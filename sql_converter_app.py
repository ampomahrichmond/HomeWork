import streamlit as st
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

st.set_page_config(
    page_title="SQL Converter for Collibra",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stApp > header {
        background-color: transparent;
    }
    .stApp {
        background: linear-gradient(135deg, #00a651 0%, #007a3d 100%);
        background-attachment: fixed;
    }
    .main .block-container {
        background-color: white;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 1rem;
    }
    .stButton > button {
        background-color: #00a651;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: background-color 0.3s;
    }
    .stButton > button:hover {
        background-color: #007a3d;
    }
    .stSelectbox > div > div {
        background-color: #f0f8f0;
    }
    .stTextArea > div > div > textarea {
        background-color: #f0f8f0;
    }
    .stFileUploader > div {
        background-color: #f0f8f0;
        border: 2px dashed #00a651;
        border-radius: 5px;
    }
    h1, h2, h3 {
        color: #007a3d;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

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
    
    def convert_sql_to_collibra(self, sql_text):
        """Convert SQL by adding @ before table names after specific keywords"""
        if not sql_text or not sql_text.strip():
            return sql_text
        
        converted_sql = sql_text
        
        for keyword in self.sql_keywords:
            pattern = f'({keyword})([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)'
            
            def replace_func(match):
                keyword_part = match.group(1)
                table_part = match.group(2)
                if not table_part.startswith('@'):
                    return f"{keyword_part}@{table_part}"
                return match.group(0)
            
            converted_sql = re.sub(pattern, replace_func, converted_sql, flags=re.IGNORECASE)
        
        return converted_sql
    
    def process_excel_file(self, uploaded_file):
        """Process uploaded Excel file and convert SQL statements"""
        try:
            df = pd.read_excel(uploaded_file)
            
            sql_column = None
            for col in df.columns:
                if col.lower() == 'sql':
                    sql_column = col
                    break
            
            if sql_column is None:
                return None, "No 'SQL' column found in the Excel file"
            
            df['Original_SQL'] = df[sql_column]
            df['Collibra_SQL'] = df[sql_column].apply(self.convert_sql_to_collibra)
            
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

def create_download_link(df, filename, file_format='excel'):
    """Create download link for dataframe"""
    if file_format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='SQL_Conversion')
        output.seek(0)
        b64 = base64.b64encode(output.read()).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">Download Excel File</a>'
    elif file_format == 'json':
        json_string = df.to_json(orient='records', indent=2)
        b64 = base64.b64encode(json_string.encode()).decode()
        href = f'<a href="data:application/json;base64,{b64}" download="{filename}.json">Download JSON File</a>'
    
    return href

def main():
    if 'converter' not in st.session_state:
        st.session_state.converter = SQLConverter()
    if 'db_connector' not in st.session_state:
        st.session_state.db_connector = DatabaseConnector()
    if 'converted_data' not in st.session_state:
        st.session_state.converted_data = None

    st.title("🔄 SQL Converter for Collibra")
    st.markdown("Convert SQL statements to Collibra format by adding @ before table references")
    
    with st.sidebar:
        st.header("🔗 Database Connections")
        
        db_type = st.selectbox(
            "Select Database Type",
            ["None", "SQLite", "PostgreSQL", "Oracle"]
        )
        
        if db_type != "None":
            st.subheader(f"Connect to {db_type}")
            
            if db_type == "SQLite":
                db_path = st.text_input("Database Path", placeholder="/path/to/database.db")
                if st.button("Connect to SQLite"):
                    if db_path:
                        conn, error = st.session_state.db_connector.connect_sqlite(db_path)
                        if conn:
                            st.success("Connected to SQLite successfully!")
                            st.session_state.db_connection = conn
                        else:
                            st.error(error)
            
            elif db_type == "PostgreSQL":
                host = st.text_input("Host", value="localhost")
                port = st.text_input("Port", value="5432")
                database = st.text_input("Database Name")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.button("Connect to PostgreSQL"):
                    if all([host, port, database, username, password]):
                        conn, error = st.session_state.db_connector.connect_postgresql(
                            host, port, database, username, password
                        )
                        if conn:
                            st.success("Connected to PostgreSQL successfully!")
                            st.session_state.db_connection = conn
                        else:
                            st.error(error)
            
            elif db_type == "Oracle":
                host = st.text_input("Host", value="localhost")
                port = st.text_input("Port", value="1521")
                service_name = st.text_input("Service Name")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.button("Connect to Oracle"):
                    if all([host, port, service_name, username, password]):
                        conn, error = st.session_state.db_connector.connect_oracle(
                            host, port, service_name, username, password
                        )
                        if conn:
                            st.success("Connected to Oracle successfully!")
                            st.session_state.db_connection = conn
                        else:
                            st.error(error)
        
        st.header("🏛️ Collibra Connection")
        collibra_url = st.text_input("Collibra URL", placeholder="https://your-collibra-instance.com")
        collibra_username = st.text_input("Collibra Username")
        collibra_password = st.text_input("Collibra Password", type="password")
        
        if st.button("Connect to Collibra"):
            if all([collibra_url, collibra_username, collibra_password]):
                st.info("Collibra connection feature would be implemented with Collibra REST API")
            else:
                st.warning("Please fill in all Collibra connection fields")

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Input Methods")
        
        input_method = st.radio(
            "Choose input method:",
            ["Manual SQL Input", "Excel File Upload"]
        )
        
        if input_method == "Manual SQL Input":
            st.subheader("Enter SQL Statement")
            sql_input = st.text_area(
                "SQL Statement",
                height=200,
                placeholder="SELECT * FROM DB2.ADR_XY3 WHERE condition = 'value'"
            )
            
            if st.button("Convert SQL", type="primary"):
                if sql_input.strip():
                    converted_sql = st.session_state.converter.convert_sql_to_collibra(sql_input)
                    
                    df = pd.DataFrame({
                        'Original_SQL': [sql_input],
                        'Collibra_SQL': [converted_sql]
                    })
                    st.session_state.converted_data = df
                    
                    st.markdown('<div class="success-box">✅ SQL converted successfully!</div>', unsafe_allow_html=True)
                else:
                    st.error("Please enter a SQL statement")
        
        elif input_method == "Excel File Upload":
            st.subheader("Upload Excel File")
            uploaded_file = st.file_uploader(
                "Choose Excel file",
                type=['xlsx', 'xls'],
                help="Excel file should contain a column named 'SQL' with SQL statements"
            )
            
            if uploaded_file is not None:
                if st.button("Process Excel File", type="primary"):
                    df, error = st.session_state.converter.process_excel_file(uploaded_file)
                    
                    if df is not None:
                        st.session_state.converted_data = df
                        st.markdown('<div class="success-box">✅ Excel file processed successfully!</div>', unsafe_allow_html=True)
                        st.write(f"Processed {len(df)} SQL statements")
                    else:
                        st.markdown(f'<div class="error-box">❌ {error}</div>', unsafe_allow_html=True)
    
    with col2:
        st.header("📊 Results & Preview")
        
        if st.session_state.converted_data is not None:
            df = st.session_state.converted_data
            
            st.subheader("Preview")
            st.dataframe(df, use_container_width=True)
            
            st.subheader("📥 Download Options")
            
            col_download1, col_download2 = st.columns(2)
            
            with col_download1:
                if st.button("Download as Excel", type="secondary"):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"sql_conversion_{timestamp}"
                    download_link = create_download_link(df, filename, 'excel')
                    st.markdown(download_link, unsafe_allow_html=True)
            
            with col_download2:
                if st.button("Download as JSON", type="secondary"):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"sql_conversion_{timestamp}"
                    download_link = create_download_link(df, filename, 'json')
                    st.markdown(download_link, unsafe_allow_html=True)
            
            st.subheader("🔍 Side-by-Side Comparison")
            for idx, row in df.iterrows():
                with st.expander(f"SQL Statement {idx + 1}"):
                    col_orig, col_conv = st.columns(2)
                    
                    with col_orig:
                        st.markdown("**Original SQL:**")
                        st.code(row['Original_SQL'], language='sql')
                    
                    with col_conv:
                        st.markdown("**Collibra SQL:**")
                        st.code(row['Collibra_SQL'], language='sql')
        else:
            st.info("👆 Use the input methods on the left to convert SQL statements")
    
    if 'db_connection' in st.session_state:
        st.header("🗄️ Database Query Execution")
        
        query_input = st.text_area(
            "Enter SQL Query to Execute",
            height=100,
            placeholder="SELECT * FROM your_table LIMIT 10"
        )
        
        if st.button("Execute Query"):
            if query_input.strip():
                df_result, error = st.session_state.db_connector.execute_query(
                    st.session_state.db_connection, query_input
                )
                
                if df_result is not None:
                    st.subheader("Query Results")
                    st.dataframe(df_result, use_container_width=True)
                else:
                    st.error(error)
    
    st.markdown("---")
    st.markdown(
        "**SQL Converter for Collibra** | Built with Streamlit | "
        "Supports SQLite, PostgreSQL, Oracle databases"
    )

if __name__ == "__main__":
    main()
