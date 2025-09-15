from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for
import pandas as pd
import re
import json
import io
import sqlite3
import psycopg2
from sqlalchemy import create_engine
import openpyxl
from datetime import datetime
import base64
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class SQLConverter:
    def __init__(self):
        self.sql_keywords = [
            r'\bFROM\s+',
            r'\bJOIN\s+',
            r'\bINNER\s+JOIN\s+',
            r'\bLEFT\s+JOIN\s+',
            r'\bRIGHT\s+JOIN\s+',
            r'\bFULL\s+JOIN\s+',
            r'\bCROSS\s+JOIN\s+',
            r'\bLEFT\s+OUTER\s+JOIN\s+',
            r'\bRIGHT\s+OUTER\s+JOIN\s+',
            r'\bFULL\s+OUTER\s+JOIN\s+'
        ]
    
    def convert_sql_to_collibra(self, sql_text, use_alias_conversion=False, flatten_arrays_flag=False, flatten_deep_structures_flag=False, unwrap_ctes_flag=False):
        """Convert SQL by adding @ before table names after specific keywords"""
        if not sql_text or not sql_text.strip():
            return sql_text
        
        converted_sql = sql_text
        
        if unwrap_ctes_flag:
            converted_sql = self.unwrap_ctes(converted_sql)
        
        if flatten_deep_structures_flag:
            converted_sql = self.flatten_deep_structures(converted_sql)
        elif flatten_arrays_flag:
            converted_sql = self.flatten_arrays(converted_sql)
        
        if use_alias_conversion:
            converted_sql, alias_mapping = self.convert_table_aliases(converted_sql)
            if alias_mapping:
                return converted_sql
        
        for keyword in self.sql_keywords:
            pattern = f'({keyword})([a-zA-Z_][a-zA-Z0-9_]*(?:\\.[a-zA-Z_][a-zA-Z0-9_]*)*)'
            
            def replace_func(match):
                keyword_part = match.group(1)
                table_part = match.group(2)
                if not table_part.startswith('@'):
                    return f"{keyword_part}@{table_part}"
                return match.group(0)
            
            converted_sql = re.sub(pattern, replace_func, converted_sql, flags=re.IGNORECASE)
        
        return converted_sql
    
    def detect_arrays(self, sql_text):
        """Detect nested arrays and array indexing in SQL"""
        array_patterns = [
            r'\w+\[\d+\]',
            r'ARRAY_AGG\s*\(',
            r'UNNEST\s*\(',
            r'\w+\[\w+\]\.\w+',
            r'\w+\.\w+\[\d+\]',
        ]
        
        detected_arrays = []
        for pattern in array_patterns:
            matches = re.findall(pattern, sql_text, re.IGNORECASE)
            detected_arrays.extend(matches)
        
        return detected_arrays
    
    def convert_table_aliases(self, sql_text):
        """Convert table aliases to @this/@input1 format"""
        if not sql_text or not sql_text.strip():
            return sql_text, {}
        
        alias_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        aliases = re.findall(alias_pattern, sql_text, re.IGNORECASE)
        
        if not aliases:
            return sql_text, {}
        
        alias_mapping = {}
        converted_sql = sql_text
        
        for i, (table_name, alias) in enumerate(aliases):
            if i == 0:
                new_alias = '@this'
            else:
                new_alias = f'@input{i}'
            
            alias_mapping[alias] = new_alias
            
            pattern = f'({re.escape(table_name)}\\s+){re.escape(alias)}'
            replacement = f'{new_alias}'
            converted_sql = re.sub(pattern, replacement, converted_sql, flags=re.IGNORECASE)
        
        for old_alias, new_alias in alias_mapping.items():
            column_pattern = f'\\b{re.escape(old_alias)}\\.([a-zA-Z_][a-zA-Z0-9_]*)'
            column_replacement = f'{new_alias}.\\1'
            converted_sql = re.sub(column_pattern, column_replacement, converted_sql, flags=re.IGNORECASE)
        
        return converted_sql, alias_mapping
    
    def flatten_arrays(self, sql_text):
        """Attempt to flatten array structures for Collibra compatibility"""
        flattened_sql = sql_text
        
        array_index_pattern = r'(\w+)\[(\d+)\]\.(\w+)'
        
        def replace_array_access(match):
            table_name = match.group(1)
            index = match.group(2)
            field = match.group(3)
            return f"flattened_{table_name}.{field}"
        
        flattened_sql = re.sub(array_index_pattern, replace_array_access, flattened_sql, flags=re.IGNORECASE)
        
        if re.search(r'flattened_\w+', flattened_sql):
            from_pattern = r'(FROM\s+)(@?\w+(?:\.\w+)*)'
            
            def add_unnest(match):
                from_clause = match.group(1)
                table_name = match.group(2)
                return f"{from_clause}{table_name}, UNNEST({table_name}.orders) AS flattened_orders"
            
            flattened_sql = re.sub(from_pattern, add_unnest, flattened_sql, flags=re.IGNORECASE)
        
        return flattened_sql
    
    def detect_deep_nesting(self, sql_text):
        """Detect deeply nested arrays, STRUCTs, and CTEs"""
        deep_nesting_patterns = {
            'array_agg_struct': r'ARRAY_AGG\s*\(\s*STRUCT\s*\(',
            'nested_array_agg': r'ARRAY_AGG\s*\([^)]*ARRAY_AGG',
            'multi_level_unnest': r'UNNEST\s*\([^)]*UNNEST',
            'struct_in_array': r'STRUCT\s*\([^)]*\[\d+\]',
            'cte_with_clause': r'\bWITH\s+\w+\s+AS\s*\(',
            'nested_struct_access': r'\w+\.\w+\.\w+\[\d+\]\.\w+',
            'complex_aggregation': r'ARRAY_AGG\s*\([^)]*GROUP\s+BY[^)]*\)'
        }
        
        detected_patterns = {}
        complexity_score = 0
        
        for pattern_name, pattern in deep_nesting_patterns.items():
            matches = re.findall(pattern, sql_text, re.IGNORECASE | re.DOTALL)
            if matches:
                detected_patterns[pattern_name] = matches
                complexity_score += len(matches)
        
        return detected_patterns, complexity_score
    
    def detect_ctes(self, sql_text):
        """Detect Common Table Expressions (WITH clauses)"""
        cte_pattern = r'\bWITH\s+(\w+)\s+AS\s*\(([^)]+(?:\([^)]*\)[^)]*)*)\)'
        ctes = re.findall(cte_pattern, sql_text, re.IGNORECASE | re.DOTALL)
        
        cte_info = []
        for cte_name, cte_body in ctes:
            cte_info.append({
                'name': cte_name,
                'body': cte_body.strip(),
                'complexity': len(re.findall(r'\b(?:SELECT|FROM|JOIN|WHERE|GROUP BY|ORDER BY)\b', cte_body, re.IGNORECASE))
            })
        
        return cte_info
    
    def flatten_deep_structures(self, sql_text):
        """Advanced flattening for deeply nested structures"""
        flattened_sql = sql_text
        alias_counter = 0
        
        array_struct_pattern = r'ARRAY_AGG\s*\(\s*STRUCT\s*\(([^)]+)\)\s*\)'
        
        def replace_array_struct(match):
            nonlocal alias_counter
            struct_fields = match.group(1)
            alias_counter += 1
            
            if alias_counter == 1:
                flat_alias = 'store_flat'
            elif alias_counter == 2:
                flat_alias = 'category_flat'
            elif alias_counter == 3:
                flat_alias = 'product_flat'
            else:
                flat_alias = f'level_{alias_counter}_flat'
            
            return f"UNNEST(ARRAY[{struct_fields}]) AS {flat_alias}"
        
        flattened_sql = re.sub(array_struct_pattern, replace_array_struct, flattened_sql, flags=re.IGNORECASE | re.DOTALL)
        
        nested_unnest_pattern = r'UNNEST\s*\([^)]*UNNEST\s*\([^)]+\)[^)]*\)'
        
        def replace_nested_unnest(match):
            nonlocal alias_counter
            alias_counter += 1
            flat_alias = f'unnest_level_{alias_counter}'
            return f"UNNEST(...) AS {flat_alias}"
        
        flattened_sql = re.sub(nested_unnest_pattern, replace_nested_unnest, flattened_sql, flags=re.IGNORECASE)
        
        subquery_order_pattern = r'\(\s*SELECT[^)]*ORDER\s+BY[^)]*\)'
        flattened_sql = re.sub(subquery_order_pattern, lambda m: m.group(0).replace('ORDER BY', '-- ORDER BY'), flattened_sql, flags=re.IGNORECASE)
        
        return flattened_sql
    
    def unwrap_ctes(self, sql_text):
        """Attempt to inline CTEs where feasible"""
        ctes = self.detect_ctes(sql_text)
        unwrapped_sql = sql_text
        
        for cte in ctes:
            if cte['complexity'] <= 3:  # Only inline simple CTEs
                cte_ref_pattern = f'\\b{re.escape(cte["name"])}\\b'
                inline_replacement = f"({cte['body']})"
                unwrapped_sql = re.sub(cte_ref_pattern, inline_replacement, unwrapped_sql, flags=re.IGNORECASE)
        
        with_pattern = r'\bWITH\s+\w+\s+AS\s*\([^)]+(?:\([^)]*\)[^)]*)*\)\s*,?\s*'
        unwrapped_sql = re.sub(with_pattern, '', unwrapped_sql, flags=re.IGNORECASE | re.DOTALL)
        
        return unwrapped_sql
    
    def process_excel_file(self, file_path):
        """Process uploaded Excel file and convert SQL statements"""
        try:
            df = pd.read_excel(file_path)
            
            sql_column = None
            for col in df.columns:
                if col.lower() == 'sql':
                    sql_column = col
                    break
            
            if sql_column is None:
                return None, "No 'SQL' column found in the Excel file"
            
            df['Original_SQL'] = df[sql_column]
            df['Collibra_SQL'] = df[sql_column].apply(lambda x: self.convert_sql_to_collibra(x, use_alias_conversion=True))
            
            result_df = df[['Original_SQL', 'Collibra_SQL']].copy()
            
            return result_df, None
            
        except Exception as e:
            return None, f"Error processing Excel file: {str(e)}"

class DatabaseConnector:
    def __init__(self):
        self.connections = {}
    
    def connect_sqlite(self, db_path):
        """Connect to SQLite database"""
        try:
            conn = sqlite3.connect(db_path)
            return conn, None
        except Exception as e:
            return None, f"SQLite connection error: {str(e)}"
    
    def connect_postgresql(self, host, port, database, username, password):
        """Connect to PostgreSQL database"""
        try:
            conn_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            engine = create_engine(conn_string)
            conn = engine.connect()
            return conn, None
        except Exception as e:
            return None, f"PostgreSQL connection error: {str(e)}"
    
    def connect_oracle(self, host, port, service_name, username, password):
        """Connect to Oracle database"""
        try:
            import cx_Oracle
            dsn = cx_Oracle.makedsn(host, port, service_name=service_name)
            conn = cx_Oracle.connect(username, password, dsn)
            return conn, None
        except Exception as e:
            return None, f"Oracle connection error: {str(e)}"
    
    def execute_query(self, conn, query):
        """Execute query and return results"""
        try:
            if isinstance(conn, sqlite3.Connection):
                df = pd.read_sql_query(query, conn)
            else:
                df = pd.read_sql_query(query, conn)
            return df, None
        except Exception as e:
            return None, f"Query execution error: {str(e)}"

converter = SQLConverter()
db_connector = DatabaseConnector()
converted_data = None
current_sql = None
detected_arrays = []
detected_deep_nesting = {}
complexity_score = 0
detected_ctes = []

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SQL Converter for Collibra</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #00a651 0%, #007a3d 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #00a651 0%, #007a3d 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            padding: 30px;
        }
        
        .sidebar {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .section {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .section h2 {
            color: #007a3d;
            margin-bottom: 20px;
            font-size: 1.5em;
        }
        
        .section h3 {
            color: #007a3d;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        
        .form-control {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #00a651;
        }
        
        textarea.form-control {
            resize: vertical;
            min-height: 150px;
            font-family: 'Courier New', monospace;
        }
        
        .btn {
            background: #00a651;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.3s;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }
        
        .btn:hover {
            background: #007a3d;
        }
        
        .btn-secondary {
            background: #6c757d;
        }
        
        .btn-secondary:hover {
            background: #545b62;
        }
        
        .btn-small {
            padding: 8px 16px;
            font-size: 14px;
        }
        
        .file-upload {
            border: 2px dashed #00a651;
            border-radius: 8px;
            padding: 30px;
            text-align: center;
            background: #f0f8f0;
            transition: background-color 0.3s;
        }
        
        .file-upload:hover {
            background: #e8f5e8;
        }
        
        .file-upload input[type="file"] {
            margin: 10px 0;
        }
        
        .radio-group {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .radio-group label {
            display: flex;
            align-items: center;
            cursor: pointer;
        }
        
        .radio-group input[type="radio"] {
            margin-right: 8px;
        }
        
        .success {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        
        .error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        
        .table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        
        .table th,
        .table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        
        .table th {
            background: #00a651;
            color: white;
            font-weight: 600;
        }
        
        .table tr:hover {
            background: #f5f5f5;
        }
        
        .code-block {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            white-space: pre-wrap;
            margin: 10px 0;
        }
        
        .comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }
        
        .comparison-item {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
        }
        
        .comparison-item h4 {
            color: #007a3d;
            margin-bottom: 10px;
        }
        
        .download-buttons {
            display: flex;
            gap: 15px;
            margin: 20px 0;
        }
        
        .footer {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }
        
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .comparison {
                grid-template-columns: 1fr;
            }
            
            .download-buttons {
                flex-direction: column;
            }
        }
    </style>
    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(function() {
                alert('SQL copied to clipboard!');
            }, function(err) {
                console.error('Could not copy text: ', err);
                // Fallback for older browsers
                var textArea = document.createElement("textarea");
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    document.execCommand('copy');
                    alert('SQL copied to clipboard!');
                } catch (err) {
                    alert('Failed to copy SQL to clipboard');
                }
                document.body.removeChild(textArea);
            });
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔄 SQL Converter for Collibra</h1>
            <p>Convert SQL statements to Collibra format by adding @ before table references</p>
        </div>
        
        <div class="main-content">
            <!-- Left Column - Input Methods -->
            <div>
                <div class="section">
                    <h2>📝 Input Methods</h2>
                    
                    <div class="radio-group">
                        <label>
                            <input type="radio" name="input_method" value="manual" checked onchange="toggleInputMethod()">
                            Manual SQL Input
                        </label>
                        <label>
                            <input type="radio" name="input_method" value="excel" onchange="toggleInputMethod()">
                            Excel File Upload
                        </label>
                    </div>
                    
                    <!-- Manual SQL Input -->
                    <div id="manual-input" class="input-method">
                        <form action="/convert_manual" method="post">
                            <div class="form-group">
                                <label for="sql_input">SQL Statement:</label>
                                <textarea name="sql_input" id="sql_input" class="form-control" 
                                         placeholder="SELECT * FROM DB2.ADR_XY3 WHERE condition = 'value'"></textarea>
                            </div>
                            <button type="submit" class="btn">Convert SQL</button>
                        </form>
                    </div>
                    
                    <!-- Excel File Upload -->
                    <div id="excel-input" class="input-method" style="display: none;">
                        <form action="/convert_excel" method="post" enctype="multipart/form-data">
                            <div class="file-upload">
                                <h3>Upload Excel File</h3>
                                <p>Excel file should contain a column named 'SQL' with SQL statements</p>
                                <input type="file" name="excel_file" accept=".xlsx,.xls" required>
                                <br>
                                <button type="submit" class="btn">Process Excel File</button>
                            </div>
                        </form>
                    </div>
                </div>
                
                <!-- Database Connections -->
                <div class="section">
                    <h2>🔗 Database Connections</h2>
                    
                    <div class="form-group">
                        <label for="db_type">Select Database Type:</label>
                        <select id="db_type" class="form-control" onchange="toggleDbForm()">
                            <option value="">None</option>
                            <option value="sqlite">SQLite</option>
                            <option value="postgresql">PostgreSQL</option>
                            <option value="oracle">Oracle</option>
                        </select>
                    </div>
                    
                    <!-- SQLite Form -->
                    <div id="sqlite-form" class="db-form" style="display: none;">
                        <form action="/connect_sqlite" method="post">
                            <div class="form-group">
                                <label for="db_path">Database Path:</label>
                                <input type="text" name="db_path" class="form-control" placeholder="/path/to/database.db">
                            </div>
                            <button type="submit" class="btn btn-small">Connect to SQLite</button>
                        </form>
                    </div>
                    
                    <!-- PostgreSQL Form -->
                    <div id="postgresql-form" class="db-form" style="display: none;">
                        <form action="/connect_postgresql" method="post">
                            <div class="form-group">
                                <label for="pg_host">Host:</label>
                                <input type="text" name="host" class="form-control" value="localhost">
                            </div>
                            <div class="form-group">
                                <label for="pg_port">Port:</label>
                                <input type="text" name="port" class="form-control" value="5432">
                            </div>
                            <div class="form-group">
                                <label for="pg_database">Database Name:</label>
                                <input type="text" name="database" class="form-control">
                            </div>
                            <div class="form-group">
                                <label for="pg_username">Username:</label>
                                <input type="text" name="username" class="form-control">
                            </div>
                            <div class="form-group">
                                <label for="pg_password">Password:</label>
                                <input type="password" name="password" class="form-control">
                            </div>
                            <button type="submit" class="btn btn-small">Connect to PostgreSQL</button>
                        </form>
                    </div>
                    
                    <!-- Oracle Form -->
                    <div id="oracle-form" class="db-form" style="display: none;">
                        <form action="/connect_oracle" method="post">
                            <div class="form-group">
                                <label for="ora_host">Host:</label>
                                <input type="text" name="host" class="form-control" value="localhost">
                            </div>
                            <div class="form-group">
                                <label for="ora_port">Port:</label>
                                <input type="text" name="port" class="form-control" value="1521">
                            </div>
                            <div class="form-group">
                                <label for="ora_service">Service Name:</label>
                                <input type="text" name="service_name" class="form-control">
                            </div>
                            <div class="form-group">
                                <label for="ora_username">Username:</label>
                                <input type="text" name="username" class="form-control">
                            </div>
                            <div class="form-group">
                                <label for="ora_password">Password:</label>
                                <input type="password" name="password" class="form-control">
                            </div>
                            <button type="submit" class="btn btn-small">Connect to Oracle</button>
                        </form>
                    </div>
                </div>
                
                <!-- Collibra Connection -->
                <div class="section">
                    <h2>🏛️ Collibra Connection</h2>
                    <form action="/connect_collibra" method="post">
                        <div class="form-group">
                            <label for="collibra_url">Collibra URL:</label>
                            <input type="url" name="collibra_url" class="form-control" 
                                   placeholder="https://your-collibra-instance.com">
                        </div>
                        <div class="form-group">
                            <label for="collibra_username">Username:</label>
                            <input type="text" name="collibra_username" class="form-control">
                        </div>
                        <div class="form-group">
                            <label for="collibra_password">Password:</label>
                            <input type="password" name="collibra_password" class="form-control">
                        </div>
                        <button type="submit" class="btn btn-small">Connect to Collibra</button>
                    </form>
                </div>
            </div>
            
            <!-- Right Column - Results -->
            <div>
                <div class="section">
                    <h2>📊 Results & Preview</h2>
                    
                    {% if message %}
                        <div class="{% if 'success' in message_type %}success{% else %}error{% endif %}">
                            {{ message }}
                        </div>
                    {% endif %}
                    
                    {% if detected_arrays %}
                        <div class="error">
                            <h4>⚠️ Arrays detected in query</h4>
                            <p>Detected array structures: {{ detected_arrays|join(', ') }}</p>
                            <p>Collibra DQ does not natively support nested arrays. Click below to flatten:</p>
                            <form action="/flatten_arrays" method="post" style="margin-top: 10px;">
                                <button type="submit" class="btn" title="Automatically converts array structures to flattened form supported by Collibra">
                                    🔧 Flatten Arrays and Regenerate Query
                                </button>
                            </form>
                        </div>
                    {% endif %}
                    
                    {% if detected_deep_nesting and complexity_score > 0 %}
                        <div class="error" style="background: #fff3cd; border-color: #ffeaa7; color: #856404;">
                            <h4>⚠️ Deep nesting detected in query</h4>
                            <p><strong>Complexity Score: {{ complexity_score }}</strong></p>
                            <p>This SQL query contains deeply nested arrays and STRUCTs using multiple levels of ARRAY_AGG, UNNEST, and STRUCT combinations. Collibra DQ does not support evaluating multi-layer nested structures or complex object aggregation.</p>
                            
                            <details style="margin: 10px 0;">
                                <summary style="cursor: pointer; font-weight: bold;">🔍 View Detected Patterns</summary>
                                <ul style="margin: 10px 0; padding-left: 20px;">
                                    {% for pattern_name, matches in detected_deep_nesting.items() %}
                                    <li><strong>{{ pattern_name.replace('_', ' ').title() }}:</strong> {{ matches|length }} occurrence(s)</li>
                                    {% endfor %}
                                </ul>
                            </details>
                            
                            <p><strong>✅ Click [Flatten and Simplify Query] to automatically generate a flattened version suitable for Collibra.</strong></p>
                            <p><em>ℹ️ Note: This will preserve semantic intent but may restructure deeply aggregated layers into flat tabular form. For large multi-step queries, consider breaking into materialized views before ingestion.</em></p>
                            
                            <form action="/flatten_deep_structures" method="post" style="margin-top: 10px;">
                                <button type="submit" class="btn" style="background: #e17055; border-color: #d63031;" title="Automatically converts deep nested structures to flattened form with smart aliasing">
                                    🔧 Flatten and Simplify Query
                                </button>
                            </form>
                        </div>
                    {% endif %}
                    
                    {% if detected_ctes and detected_ctes|length > 0 %}
                        <div class="error" style="background: #e3f2fd; border-color: #90caf9; color: #1565c0;">
                            <h4>ℹ️ Common Table Expressions (CTEs) detected</h4>
                            <p>Found {{ detected_ctes|length }} CTE(s) in your query:</p>
                            
                            <details style="margin: 10px 0;">
                                <summary style="cursor: pointer; font-weight: bold;">🔍 View CTE Details</summary>
                                <ul style="margin: 10px 0; padding-left: 20px;">
                                    {% for cte in detected_ctes %}
                                    <li><strong>{{ cte.name }}:</strong> Complexity {{ cte.complexity }} 
                                        {% if cte.complexity <= 3 %}<em>(can be inlined)</em>{% else %}<em>(recommend materialization)</em>{% endif %}
                                    </li>
                                    {% endfor %}
                                </ul>
                            </details>
                            
                            <p>For simple CTEs, you can inline them for Collibra compatibility:</p>
                            <form action="/unwrap_ctes" method="post" style="margin-top: 10px;">
                                <button type="submit" class="btn" style="background: #0984e3; border-color: #74b9ff;" title="Unwrap and inline CTEs where feasible">
                                    🔧 Unwrap and Inline CTEs
                                </button>
                            </form>
                        </div>
                    {% endif %}
                    
                    {% if converted_data %}
                        <h3>Preview</h3>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Original SQL</th>
                                    <th>Collibra SQL</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for row in converted_data %}
                                <tr>
                                    <td>{{ row['Original_SQL'][:100] }}{% if row['Original_SQL']|length > 100 %}...{% endif %}</td>
                                    <td>{{ row['Collibra_SQL'][:100] }}{% if row['Collibra_SQL']|length > 100 %}...{% endif %}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        
                        <h3>📥 Interactive Query Actions</h3>
                        <div class="download-buttons">
                            <a href="/download/excel" class="btn">📊 Download as Excel</a>
                            <a href="/download/json" class="btn btn-secondary">📄 Download as JSON</a>
                            <a href="/download/sql" class="btn btn-secondary">💾 Download as .sql</a>
                            <button onclick="copyToClipboard('{{ converted_data[0].Collibra_SQL|replace("'", "\\'") }}')" class="btn btn-secondary">📋 Copy to Clipboard</button>
                            {% if converted_data|length == 1 %}
                            <form action="/send_to_collibra" method="post" style="display: inline;">
                                <button type="submit" class="btn" style="background: #007a3d;">🏛️ Send to Collibra</button>
                            </form>
                            {% endif %}
                        </div>
                        
                        <h3>🔍 Side-by-Side Comparison</h3>
                        {% for row in converted_data %}
                        <div class="comparison">
                            <div class="comparison-item">
                                <h4>Original SQL:</h4>
                                <div class="code-block" id="original-sql">{{ row['Original_SQL'] }}</div>
                            </div>
                            <div class="comparison-item">
                                <h4>Collibra SQL:</h4>
                                <div class="code-block" id="collibra-sql">{{ row['Collibra_SQL'] }}</div>
                                {% if loop.index == 1 and converted_data|length == 1 %}
                                <div style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
                                    <button onclick="copyToClipboard('{{ row.Collibra_SQL|replace("'", "\\'") }}')" class="btn" style="font-size: 12px; padding: 5px 10px;">
                                        📋 Copy to Clipboard
                                    </button>
                                    <a href="/download/sql" class="btn" style="font-size: 12px; padding: 5px 10px; text-decoration: none; display: inline-block;">
                                        💾 Download as .sql
                                    </a>
                                    <form action="/send_to_collibra" method="post" style="display: inline;">
                                        <button type="submit" class="btn" style="font-size: 12px; padding: 5px 10px;">
                                            🏛️ Send to Collibra
                                        </button>
                                    </form>
                                </div>
                                {% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <p>👆 Use the input methods on the left to convert SQL statements</p>
                    {% endif %}
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>SQL Converter for Collibra</strong> | Built with Flask | Supports SQLite, PostgreSQL, Oracle databases</p>
        </div>
    </div>
    
    <script>
        function toggleInputMethod() {
            const manualInput = document.getElementById('manual-input');
            const excelInput = document.getElementById('excel-input');
            const selectedMethod = document.querySelector('input[name="input_method"]:checked').value;
            
            if (selectedMethod === 'manual') {
                manualInput.style.display = 'block';
                excelInput.style.display = 'none';
            } else {
                manualInput.style.display = 'none';
                excelInput.style.display = 'block';
            }
        }
        
        function toggleDbForm() {
            const dbType = document.getElementById('db_type').value;
            const forms = document.querySelectorAll('.db-form');
            
            forms.forEach(form => form.style.display = 'none');
            
            if (dbType) {
                const selectedForm = document.getElementById(dbType + '-form');
                if (selectedForm) {
                    selectedForm.style.display = 'block';
                }
            }
        }
        
        function copyToClipboard(text) {
            if (text) {
                navigator.clipboard.writeText(text).then(function() {
                    alert('✅ Collibra SQL copied to clipboard!');
                }, function(err) {
                    console.error('Could not copy text: ', err);
                    // Fallback for older browsers
                    const textArea = document.createElement('textarea');
                    textArea.value = text;
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textArea);
                    alert('✅ Collibra SQL copied to clipboard!');
                });
            } else {
                const collibraSql = document.getElementById('collibra-sql');
                if (collibraSql) {
                    const sqlText = collibraSql.textContent;
                    navigator.clipboard.writeText(sqlText).then(function() {
                        alert('✅ Collibra SQL copied to clipboard!');
                    }, function(err) {
                        console.error('Could not copy text: ', err);
                        const textArea = document.createElement('textarea');
                        textArea.value = sqlText;
                        document.body.appendChild(textArea);
                        textArea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textArea);
                        alert('✅ Collibra SQL copied to clipboard!');
                    });
                }
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    global converted_data, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                detected_deep_nesting=detected_deep_nesting,
                                complexity_score=complexity_score,
                                detected_ctes=detected_ctes,
                                message=None, 
                                message_type=None)

@app.route('/convert_manual', methods=['POST'])
def convert_manual():
    global converted_data, current_sql, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    
    sql_input = request.form.get('sql_input', '').strip()
    
    if not sql_input:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=None, 
                                    detected_arrays=None,
                                    detected_deep_nesting=None,
                                    complexity_score=0,
                                    detected_ctes=None,
                                    message="Please enter a SQL statement", 
                                    message_type="error")
    
    current_sql = sql_input
    
    detected_arrays = converter.detect_arrays(sql_input)
    
    detected_deep_nesting, complexity_score = converter.detect_deep_nesting(sql_input)
    
    detected_ctes = converter.detect_ctes(sql_input)
    
    converted_sql = converter.convert_sql_to_collibra(sql_input, use_alias_conversion=True)
    
    converted_data = [{
        'Original_SQL': sql_input,
        'Collibra_SQL': converted_sql
    }]
    
    message = "✅ SQL converted successfully!"
    if detected_arrays:
        message += f" (Arrays detected: {len(detected_arrays)} structures)"
    if detected_deep_nesting:
        message += f" (Deep nesting detected: complexity score {complexity_score})"
    if detected_ctes:
        message += f" (CTEs detected: {len(detected_ctes)} expressions)"
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                detected_deep_nesting=detected_deep_nesting,
                                complexity_score=complexity_score,
                                detected_ctes=detected_ctes,
                                message=message, 
                                message_type="success")

@app.route('/convert_excel', methods=['POST'])
def convert_excel():
    global converted_data, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    
    if 'excel_file' not in request.files:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=None,
                                    detected_arrays=None,
                                    detected_deep_nesting=None,
                                    complexity_score=0,
                                    detected_ctes=None,
                                    message="No file selected", 
                                    message_type="error")
    
    file = request.files['excel_file']
    
    if file.filename == '':
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=None,
                                    detected_arrays=None,
                                    detected_deep_nesting=None,
                                    complexity_score=0,
                                    detected_ctes=None,
                                    message="No file selected", 
                                    message_type="error")
    
    if file and file.filename.lower().endswith(('.xlsx', '.xls')):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        df, error = converter.process_excel_file(file_path)
        
        os.remove(file_path)
        
        if df is not None:
            converted_data = df.to_dict('records')
            detected_arrays = []
            detected_deep_nesting = {}
            complexity_score = 0
            detected_ctes = []
            return render_template_string(HTML_TEMPLATE, 
                                        converted_data=converted_data,
                                        detected_arrays=detected_arrays,
                                        detected_deep_nesting=detected_deep_nesting,
                                        complexity_score=complexity_score,
                                        detected_ctes=detected_ctes,
                                        message=f"✅ Excel file processed successfully! Processed {len(converted_data)} SQL statements", 
                                        message_type="success")
        else:
            return render_template_string(HTML_TEMPLATE, 
                                        converted_data=None,
                                        detected_arrays=None,
                                        detected_deep_nesting=None,
                                        complexity_score=0,
                                        detected_ctes=None,
                                        message=f"❌ {error}", 
                                        message_type="error")
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=None,
                                detected_arrays=None,
                                detected_deep_nesting=None,
                                complexity_score=0,
                                detected_ctes=None,
                                message="Please upload a valid Excel file (.xlsx or .xls)", 
                                message_type="error")

@app.route('/flatten_arrays', methods=['POST'])
def flatten_arrays():
    global converted_data, current_sql, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    
    if not current_sql and not converted_data:
        return redirect(url_for('index'))
    
    if current_sql:
        flattened_sql = converter.convert_sql_to_collibra(current_sql, use_alias_conversion=True, flatten_arrays_flag=True)
        converted_data = [{
            'Original_SQL': current_sql,
            'Collibra_SQL': flattened_sql
        }]
    else:
        # Flatten all SQL statements in converted_data
        for row in converted_data:
            row['Collibra_SQL'] = converter.convert_sql_to_collibra(row['Original_SQL'], use_alias_conversion=True, flatten_arrays_flag=True)
    
    detected_arrays = []
    detected_deep_nesting = {}
    complexity_score = 0
    detected_ctes = []
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                detected_deep_nesting=detected_deep_nesting,
                                complexity_score=complexity_score,
                                detected_ctes=detected_ctes,
                                message="✅ Arrays flattened successfully! Query regenerated for Collibra compatibility.", 
                                message_type="success")

@app.route('/flatten_deep_structures', methods=['POST'])
def flatten_deep_structures():
    global converted_data, current_sql, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    
    if not current_sql and not converted_data:
        return redirect(url_for('index'))
    
    if current_sql:
        flattened_sql = converter.convert_sql_to_collibra(current_sql, use_alias_conversion=True, flatten_deep_structures_flag=True)
        converted_data = [{
            'Original_SQL': current_sql,
            'Collibra_SQL': flattened_sql
        }]
    else:
        # Flatten all SQL statements in converted_data
        for row in converted_data:
            row['Collibra_SQL'] = converter.convert_sql_to_collibra(row['Original_SQL'], use_alias_conversion=True, flatten_deep_structures_flag=True)
    
    detected_arrays = []
    detected_deep_nesting = {}
    complexity_score = 0
    detected_ctes = []
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                detected_deep_nesting=detected_deep_nesting,
                                complexity_score=complexity_score,
                                detected_ctes=detected_ctes,
                                message="✅ Deep structures flattened and simplified! Query regenerated for Collibra compatibility.", 
                                message_type="success")

@app.route('/unwrap_ctes', methods=['POST'])
def unwrap_ctes():
    global converted_data, current_sql, detected_arrays, detected_deep_nesting, complexity_score, detected_ctes
    
    if not current_sql and not converted_data:
        return redirect(url_for('index'))
    
    if current_sql:
        unwrapped_sql = converter.convert_sql_to_collibra(current_sql, use_alias_conversion=True, unwrap_ctes_flag=True)
        converted_data = [{
            'Original_SQL': current_sql,
            'Collibra_SQL': unwrapped_sql
        }]
    else:
        # Unwrap CTEs in all SQL statements in converted_data
        for row in converted_data:
            row['Collibra_SQL'] = converter.convert_sql_to_collibra(row['Original_SQL'], use_alias_conversion=True, unwrap_ctes_flag=True)
    
    detected_arrays = []
    detected_deep_nesting = {}
    complexity_score = 0
    detected_ctes = []
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                detected_deep_nesting=detected_deep_nesting,
                                complexity_score=complexity_score,
                                detected_ctes=detected_ctes,
                                message="✅ CTEs unwrapped and inlined! Query regenerated for Collibra compatibility.", 
                                message_type="success")

@app.route('/download/<format>')
def download_file(format):
    global converted_data
    
    if not converted_data:
        return redirect(url_for('index'))
    
    df = pd.DataFrame(converted_data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format == 'excel':
        filename = f"sql_conversion_{timestamp}.xlsx"
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='SQL_Conversion')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    
    elif format == 'json':
        filename = f"sql_conversion_{timestamp}.json"
        json_data = df.to_json(orient='records', indent=2)
        
        output = io.BytesIO()
        output.write(json_data.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )
    
    elif format == 'sql':
        filename = f"collibra_sql_{timestamp}.sql"
        
        sql_content = "-- Collibra SQL Conversion Results\n"
        sql_content += f"-- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for i, row in enumerate(converted_data, 1):
            sql_content += f"-- Query {i}: Original SQL\n"
            sql_content += f"/*\n{row['Original_SQL']}\n*/\n\n"
            sql_content += f"-- Query {i}: Collibra SQL\n"
            sql_content += f"{row['Collibra_SQL']};\n\n"
            sql_content += "-" * 80 + "\n\n"
        
        output = io.BytesIO()
        output.write(sql_content.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )
    
    return redirect(url_for('index'))

@app.route('/send_to_collibra', methods=['POST'])
def send_to_collibra():
    global converted_data
    
    if not converted_data or len(converted_data) != 1:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="❌ Can only send single SQL statements to Collibra", 
                                    message_type="error")
    
    collibra_sql = converted_data[0]['Collibra_SQL']
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                message=f"🏛️ SQL ready for Collibra integration! (In production, this would send via REST API)", 
                                message_type="success")

@app.route('/connect_sqlite', methods=['POST'])
def connect_sqlite():
    db_path = request.form.get('db_path', '').strip()
    
    if not db_path:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="Please provide database path", 
                                    message_type="error")
    
    conn, error = db_connector.connect_sqlite(db_path)
    
    if conn:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="✅ Connected to SQLite successfully!", 
                                    message_type="success")
    else:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message=f"❌ {error}", 
                                    message_type="error")

@app.route('/connect_postgresql', methods=['POST'])
def connect_postgresql():
    host = request.form.get('host', '').strip()
    port = request.form.get('port', '').strip()
    database = request.form.get('database', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    if not all([host, port, database, username, password]):
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="Please fill in all PostgreSQL connection fields", 
                                    message_type="error")
    
    conn, error = db_connector.connect_postgresql(host, port, database, username, password)
    
    if conn:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="✅ Connected to PostgreSQL successfully!", 
                                    message_type="success")
    else:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message=f"❌ {error}", 
                                    message_type="error")

@app.route('/connect_oracle', methods=['POST'])
def connect_oracle():
    host = request.form.get('host', '').strip()
    port = request.form.get('port', '').strip()
    service_name = request.form.get('service_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    if not all([host, port, service_name, username, password]):
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="Please fill in all Oracle connection fields", 
                                    message_type="error")
    
    conn, error = db_connector.connect_oracle(host, port, service_name, username, password)
    
    if conn:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="✅ Connected to Oracle successfully!", 
                                    message_type="success")
    else:
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message=f"❌ {error}", 
                                    message_type="error")

@app.route('/connect_collibra', methods=['POST'])
def connect_collibra():
    collibra_url = request.form.get('collibra_url', '').strip()
    collibra_username = request.form.get('collibra_username', '').strip()
    collibra_password = request.form.get('collibra_password', '').strip()
    
    if not all([collibra_url, collibra_username, collibra_password]):
        return render_template_string(HTML_TEMPLATE, 
                                    converted_data=converted_data,
                                    detected_arrays=detected_arrays,
                                    message="Please fill in all Collibra connection fields", 
                                    message_type="error")
    
    return render_template_string(HTML_TEMPLATE, 
                                converted_data=converted_data,
                                detected_arrays=detected_arrays,
                                message="ℹ️ Collibra connection feature would be implemented with Collibra REST API", 
                                message_type="success")

if __name__ == '__main__':
    print("🔄 SQL Converter for Collibra")
    print("=" * 50)
    print("Starting Flask web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
