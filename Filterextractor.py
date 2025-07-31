import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import json
import re
import os
from datetime import datetime
import sqlparse
from sqlparse.sql import Where, Comparison, Identifier, Token
from sqlparse.tokens import Keyword, Operator

class SQLFilterExtractor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SQL Filter Extractor - Focused Analysis")
        self.root.geometry("1000x700")
        self.root.configure(bg='#f0f0f0')
        
        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('Title.TLabel', font=('Arial', 16, 'bold'), background='#f0f0f0')
        self.style.configure('Header.TLabel', font=('Arial', 12, 'bold'), background='#f0f0f0')
        self.style.configure('Custom.TButton', padding=10)
        
        self.selected_files = []
        self.results = []
        
        self.setup_ui()
    
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="SQL Filter Extractor - WHERE Clause Focus", style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # File selection section
        file_frame = ttk.LabelFrame(main_frame, text="File Selection", padding="15")
        file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Button(file_frame, text="📁 Select SQL Files", 
                  command=self.select_files, style='Custom.TButton').grid(row=0, column=0, padx=(0, 10))
        
        self.file_count_label = ttk.Label(file_frame, text="No files selected")
        self.file_count_label.grid(row=0, column=1)
        
        # File list
        self.file_listbox = tk.Listbox(file_frame, height=6, width=80)
        self.file_listbox.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky=(tk.W, tk.E))
        
        scrollbar = ttk.Scrollbar(file_frame, orient="vertical", command=self.file_listbox.yview)
        scrollbar.grid(row=1, column=2, sticky=(tk.N, tk.S), pady=(10, 0))
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Filter options section
        options_frame = ttk.LabelFrame(main_frame, text="Analysis Focus", padding="15")
        options_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Label(options_frame, text="✓ Focus on WHERE clause filters only (excludes JOIN conditions)", 
                 font=('Arial', 10)).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(options_frame, text="✓ Extract meaningful data filters (= inequalities, IN, LIKE, etc.)", 
                 font=('Arial', 10)).grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(options_frame, text="✗ Ignore JOIN conditions and table relationships", 
                 font=('Arial', 10), foreground='gray').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        
        self.case_sensitive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Case sensitive matching", 
                       variable=self.case_sensitive).grid(row=3, column=0, sticky=tk.W, pady=(15, 0))
        
        # Pattern matching section (optional)
        pattern_frame = ttk.LabelFrame(main_frame, text="Optional: Filter Specific Patterns", padding="15")
        pattern_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Label(pattern_frame, text="Leave blank to get ALL WHERE filters, or specify patterns to match:").grid(row=0, column=0, sticky=tk.W, columnspan=2)
        
        pattern_subframe = ttk.Frame(pattern_frame)
        pattern_subframe.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        ttk.Label(pattern_subframe, text="Column/Field contains:").grid(row=0, column=0, sticky=tk.W)
        self.var_pattern = tk.StringVar(value="")  # Empty = match all
        ttk.Entry(pattern_subframe, textvariable=self.var_pattern, width=20).grid(row=0, column=1, padx=(5, 15))
        
        ttk.Label(pattern_subframe, text="Value contains:").grid(row=0, column=2, sticky=tk.W)
        self.value_pattern = tk.StringVar(value="")  # Empty = match all
        ttk.Entry(pattern_subframe, textvariable=self.value_pattern, width=20).grid(row=0, column=3, padx=(5, 0))
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 15))
        
        ttk.Button(button_frame, text="🔍 Extract WHERE Filters", 
                  command=self.analyze_files, style='Custom.TButton').grid(row=0, column=0, padx=(0, 10))
        ttk.Button(button_frame, text="💾 Export Results", 
                  command=self.export_results, style='Custom.TButton').grid(row=0, column=1, padx=(0, 10))
        ttk.Button(button_frame, text="🗑️ Clear All", 
                  command=self.clear_all, style='Custom.TButton').grid(row=0, column=2)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 15))
        
        # Results section
        results_frame = ttk.LabelFrame(main_frame, text="WHERE Clause Filters Found", padding="15")
        results_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 0))
        
        # Results treeview - simplified columns
        columns = ('File', 'Column/Field', 'Operator', 'Value', 'Filter Condition')
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show='headings', height=12)
        
        # Adjust column widths
        self.results_tree.heading('File', text='File')
        self.results_tree.column('File', width=150, minwidth=100)
        
        self.results_tree.heading('Column/Field', text='Column/Field')
        self.results_tree.column('Column/Field', width=200, minwidth=150)
        
        self.results_tree.heading('Operator', text='Operator')
        self.results_tree.column('Operator', width=80, minwidth=60)
        
        self.results_tree.heading('Value', text='Value')
        self.results_tree.column('Value', width=150, minwidth=100)
        
        self.results_tree.heading('Filter Condition', text='Complete Filter')
        self.results_tree.column('Filter Condition', width=300, minwidth=200)
        
        self.results_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Results scrollbars
        v_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.results_tree.configure(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(results_frame, orient="horizontal", command=self.results_tree.xview)
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.results_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)
        file_frame.columnconfigure(0, weight=1)
        pattern_subframe.columnconfigure(1, weight=1)
        pattern_subframe.columnconfigure(3, weight=1)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
    
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select SQL Files",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if files:
            self.selected_files = list(files)
            self.file_listbox.delete(0, tk.END)
            for file in self.selected_files:
                self.file_listbox.insert(tk.END, os.path.basename(file))
            
            self.file_count_label.config(text=f"{len(self.selected_files)} files selected")
    
    def extract_where_filters_only(self, sql_content, filename):
        """Extract ONLY WHERE clause filters - ignore JOINs"""
        filters = []
        
        # Clean up the SQL but preserve structure
        sql_content = re.sub(r'--.*?\n', '\n', sql_content)  # Remove line comments
        sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)  # Remove block comments
        
        # Find WHERE clauses - be more flexible with the pattern
        # Look for WHERE keyword and capture everything until common end keywords or end of string
        where_pattern = r'\bWHERE\s+(.*?)(?=\s*(?:ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|UNION|;|\Z))'
        where_matches = re.finditer(where_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        print(f"Analyzing file: {filename}")  # Debug
        
        for match in where_matches:
            where_clause = match.group(1).strip()
            print(f"Found WHERE clause: {where_clause[:200]}...")  # Debug - show first 200 chars
            self.parse_where_conditions(where_clause, filename, filters)
        
        if not where_matches:
            print(f"No WHERE clauses found in {filename}")  # Debug
        
        print(f"Extracted {len(filters)} filters from {filename}")  # Debug
        return filters
    
    def parse_where_conditions(self, where_clause, filename, filters):
        """Parse individual WHERE conditions, focusing on data filters"""
        
        print(f"Parsing WHERE clause: {where_clause[:100]}...")  # Debug
        
        # Split by AND/OR using a more robust approach
        # First, let's try a simpler approach - split by AND/OR but be more lenient
        conditions = re.split(r'\s+(?:AND|OR)\s+', where_clause, flags=re.IGNORECASE)
        
        print(f"Split into {len(conditions)} conditions")  # Debug
        
        for i, condition in enumerate(conditions):
            condition = condition.strip()
            print(f"Processing condition {i+1}: {condition}")  # Debug
            
            # Skip if it's empty or too short
            if len(condition) < 3:
                print(f"  Skipped - too short")
                continue
            
            # Try to extract filter info regardless of our "is_data_filter" check initially
            filter_info = self.extract_filter_info(condition, filename)
            
            if filter_info:
                print(f"  Extracted: {filter_info['column']} {filter_info['operator']} {filter_info['value']}")
                # Apply the pattern matching
                if self.matches_user_pattern(filter_info):
                    filters.append(filter_info)
                    print(f"  Added to results!")
                else:
                    print(f"  Didn't match user pattern")
            else:
                print(f"  No filter info extracted")
                
                # If our extraction failed, let's try a simpler approach
                # Look for any condition with common operators
                simple_operators = ['=', '!=', '<>', 'LIKE', 'IN', '>', '<', '>=', '<=']
                for op in simple_operators:
                    if op in condition.upper():
                        # Simple split and add
                        parts = condition.split(op, 1)
                        if len(parts) == 2:
                            left = parts[0].strip()
                            right = parts[1].strip()
                            
                            simple_filter = {
                                'filename': filename,
                                'column': self.clean_field_name(left),
                                'operator': op,
                                'value': self.clean_value(right),
                                'full_condition': condition.strip()
                            }
                            
                            if self.matches_user_pattern(simple_filter):
                                filters.append(simple_filter)
                                print(f"  Added simple filter: {simple_filter['column']} {op} {simple_filter['value']}")
                            break
    
    def is_data_filter(self, condition):
        """Determine if this is a data filter vs a join condition"""
        
        # Skip conditions that are clearly join conditions
        # Join conditions typically have table.field = table.field pattern
        table_to_table_pattern = r'\w+\.\w+\s*=\s*\w+\.\w+$'
        if re.match(table_to_table_pattern, condition.strip()):
            return False
        
        # Skip date comparisons between fields (often used in joins)
        date_field_comparison = r'\w+\.DL_AS_OF_DT\s*=\s*\w+\.DL_AS_OF_DT$'
        if re.match(date_field_comparison, condition.strip(), re.IGNORECASE):
            return False
        
        # Look for operators that indicate data filtering
        filter_operators = ['=', '!=', '<>', '>', '<', '>=', '<=', 'LIKE', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL', 'BETWEEN']
        
        for op in filter_operators:
            if op in condition.upper():
                return True
        
        return False
    
    def extract_filter_info(self, condition, filename):
        """Extract structured information from a filter condition"""
        
        # Define operators in order of complexity (check complex ones first)
        operators = ['IS NOT NULL', 'IS NULL', 'NOT IN', '!=', '<>', '>=', '<=', 'NOT LIKE', 'LIKE', 'IN', 'BETWEEN', '=', '>', '<']
        
        for op in operators:
            # Create a more flexible pattern that handles whitespace better
            op_pattern = r'\b' + re.escape(op).replace(r'\ ', r'\s+') + r'\b'
            
            if re.search(op_pattern, condition, re.IGNORECASE):
                # Split using the same pattern
                parts = re.split(op_pattern, condition, 1, re.IGNORECASE)
                
                if len(parts) >= 2:
                    left_side = parts[0].strip()
                    right_side = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Clean up the field name
                    field = self.clean_field_name(left_side)
                    
                    # Clean up the value
                    value = self.clean_value(right_side) if right_side else "NULL"
                    
                    return {
                        'filename': filename,
                        'column': field,
                        'operator': op,
                        'value': value,
                        'full_condition': condition.strip()
                    }
                    
        # If no operator found, try a more basic approach
        # Look for simple patterns like "field = value"
        basic_pattern = r'(.+?)\s*(=|!=|<>|>=|<=|>|<)\s*(.+)'
        match = re.match(basic_pattern, condition.strip())
        if match:
            left_side = match.group(1).strip()
            operator = match.group(2).strip()
            right_side = match.group(3).strip()
            
            return {
                'filename': filename,
                'column': self.clean_field_name(left_side),
                'operator': operator,
                'value': self.clean_value(right_side),
                'full_condition': condition.strip()
            }
        
        return None
    
    def clean_field_name(self, field):
        """Clean and extract the main field name"""
        field = field.strip()
        
        # Remove function calls like NVL(), UPPER(), etc.
        field = re.sub(r'^[A-Z_]+\s*\(\s*(.+?)\s*(?:,.*?)?\)$', r'\1', field, flags=re.IGNORECASE)
        
        # If it has table.column format, just return the column part for readability
        # unless it's important to keep the table name
        if '.' in field:
            parts = field.split('.')
            table = parts[0].strip()
            column = parts[1].strip()
            return f"{table}.{column}"  # Keep both for clarity
        
        return field
    
    def clean_value(self, value):
        """Clean and format the value"""
        if not value:
            return ""
            
        value = value.strip()
        
        # Remove outer parentheses if they wrap the entire value
        if value.startswith('(') and value.endswith(')'):
            # Check if it's a list like ('1','2','3') vs a single value like ('Open')
            inner = value[1:-1].strip()
            if ',' in inner:
                # It's a list, keep the parentheses
                return value
            else:
                # Single value in parentheses, remove them
                value = inner
        
        # Remove quotes around simple values
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        return value
    
    def matches_user_pattern(self, filter_info):
        """Check if the filter matches user-specified patterns"""
        var_pattern = self.var_pattern.get().strip()
        value_pattern = self.value_pattern.get().strip()
        
        # If no patterns specified, match everything
        if not var_pattern and not value_pattern:
            return True
        
        flags = 0 if self.case_sensitive.get() else re.IGNORECASE
        
        # Check variable pattern
        if var_pattern:
            if not re.search(var_pattern, filter_info['column'], flags):
                return False
        
        # Check value pattern
        if value_pattern:
            if not re.search(value_pattern, filter_info['value'], flags):
                return False
        
        return True
    
    def analyze_files(self):
        if not self.selected_files:
            messagebox.showwarning("Warning", "Please select SQL files first.")
            return
        
        self.progress.start(10)
        self.results.clear()
        
        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        try:
            for file_path in self.selected_files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        sql_content = f.read()
                    
                    filename = os.path.basename(file_path)
                    print(f"\n=== Processing {filename} ===")  # Debug
                    filters = self.extract_where_filters_only(sql_content, filename)
                    self.results.extend(filters)
                    print(f"Total filters so far: {len(self.results)}")  # Debug
                    
                except Exception as e:
                    print(f"Error reading file {file_path}: {str(e)}")
                    messagebox.showerror("File Error", f"Error reading {file_path}: {str(e)}")
            
            # Display results in simplified format
            for result in self.results:
                self.results_tree.insert('', 'end', values=(
                    result['filename'],
                    result['column'],
                    result['operator'],
                    result['value'],
                    result['full_condition']
                ))
            
            messagebox.showinfo("Success", f"Analysis complete! Found {len(self.results)} WHERE clause filters.")
        
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during analysis: {str(e)}")
        
        finally:
            self.progress.stop()
    
    def export_results(self):
        if not self.results:
            messagebox.showwarning("Warning", "No results to export. Please analyze files first.")
            return
        
        # Prepare data for export
        export_data = []
        for result in self.results:
            export_data.append({
                'File_Name': result['filename'],
                'Column_Field': result['column'],
                'Operator': result['operator'],
                'Filter_Value': result['value'],
                'Complete_Filter_Condition': result['full_condition']
            })
        
        df = pd.DataFrame(export_data)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"sql_where_filters_{timestamp}"
        
        try:
            # Export to Excel
            excel_filename = f"{base_filename}.xlsx"
            df.to_excel(excel_filename, index=False, sheet_name='WHERE Filters')
            
            # Export to JSON
            json_filename = f"{base_filename}.json"
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("Export Complete", 
                              f"WHERE clause filters exported to:\n• {excel_filename}\n• {json_filename}")
        
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export results: {str(e)}")
    
    def clear_all(self):
        self.selected_files.clear()
        self.results.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_count_label.config(text="No files selected")
        
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        messagebox.showinfo("Cleared", "All data has been cleared.")
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    # Required packages check
    required_packages = ['pandas', 'openpyxl']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("Missing required packages. Please install:")
        print(f"pip install {' '.join(missing_packages)}")
    else:
        app = SQLFilterExtractor()
        app.run()
