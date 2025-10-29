import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
import re
import os
from html.parser import HTMLParser

class MLStripper(HTMLParser):
    """Helper class to strip HTML tags"""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    
    def handle_data(self, d):
        self.text.append(d)
    
    def get_data(self):
        return ''.join(self.text)

def strip_html_tags(html):
    """Remove HTML/XML tags from text"""
    if not html:
        return ""
    s = MLStripper()
    s.feed(html)
    text = s.get_data()
    # Also remove common XML entities and extra whitespace
    text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with single space
    text = text.strip()
    return text

def extract_urls_from_html(html):
    """Extract all URLs from HTML anchor tags and plain text"""
    if not html:
        return []
    
    urls = []
    
    # Extract from anchor tags <a href="...">
    href_pattern = r'<a[^>]+href=["\'](https?://[^"\']+)["\']'
    urls.extend(re.findall(href_pattern, html, re.IGNORECASE))
    
    # Also look for plain URLs in text (after stripping tags)
    text = strip_html_tags(html)
    url_pattern = r'(https?://[^\s]+)'
    plain_urls = re.findall(url_pattern, text)
    urls.extend(plain_urls)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        # Clean up URL (remove trailing punctuation)
        url = url.rstrip('.,;:)')
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls

class JiraXMLExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("JIRA XML to Excel Extractor")
        self.root.geometry("1200x700")
        
        # Data storage
        self.xml_files = []
        self.extracted_data = []
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="JIRA XML Data Extractor", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, pady=10)
        
        # Buttons Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, pady=10, sticky=(tk.W, tk.E))
        
        ttk.Button(button_frame, text="Load XML File(s)", 
                  command=self.load_xml_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Extract Data", 
                  command=self.extract_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export to Excel", 
                  command=self.export_to_excel).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear All", 
                  command=self.clear_all).pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_label = ttk.Label(button_frame, text="No files loaded", 
                                     foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Tab 1: Data View
        data_frame = ttk.Frame(notebook)
        notebook.add(data_frame, text="Extracted Data")
        
        # Treeview for data display
        tree_scroll_y = ttk.Scrollbar(data_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(data_frame, orient=tk.HORIZONTAL)
        
        self.tree = ttk.Treeview(data_frame, 
                                yscrollcommand=tree_scroll_y.set,
                                xscrollcommand=tree_scroll_x.set)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Tab 2: Analysis
        analysis_frame = ttk.Frame(notebook)
        notebook.add(analysis_frame, text="Analysis & Summary")
        
        self.analysis_text = tk.Text(analysis_frame, wrap=tk.WORD, 
                                    font=("Courier", 10))
        analysis_scroll = ttk.Scrollbar(analysis_frame, 
                                       command=self.analysis_text.yview)
        self.analysis_text.config(yscrollcommand=analysis_scroll.set)
        
        analysis_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.analysis_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Tab 3: Raw XML View
        raw_frame = ttk.Frame(notebook)
        notebook.add(raw_frame, text="Raw XML Preview")
        
        self.raw_text = tk.Text(raw_frame, wrap=tk.WORD, 
                               font=("Courier", 9))
        raw_scroll = ttk.Scrollbar(raw_frame, command=self.raw_text.yview)
        self.raw_text.config(yscrollcommand=raw_scroll.set)
        
        raw_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.raw_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
    def load_xml_files(self):
        """Load one or multiple XML files"""
        files = filedialog.askopenfilenames(
            title="Select XML Files",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        
        if files:
            self.xml_files = list(files)
            self.status_label.config(
                text=f"{len(self.xml_files)} file(s) loaded",
                foreground="green"
            )
            
            # Show preview of first file
            if self.xml_files:
                with open(self.xml_files[0], 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.raw_text.delete(1.0, tk.END)
                    self.raw_text.insert(1.0, content[:5000] + 
                                        "\n\n... (truncated for preview)")
    
    def parse_description_field(self, description):
        """Parse the description field to extract key-value pairs"""
        if not description:
            return {}
        
        # First, extract URLs before stripping HTML (for link fields)
        link_urls = extract_urls_from_html(description)
        
        # Strip HTML but preserve line breaks
        clean_description = strip_html_tags(description)
        
        # Dictionary to store extracted fields
        fields = {}
        
        # Define field patterns - these will match the field label and capture only its value
        # Using negative lookahead to stop at the next field or end of string
        field_patterns = [
            ('Date of Request', r'Date of Request\s*:?\s*([^\n\r]+?)(?=\s*(?:Name of Requestor|Requestor[\']*s?\s*Email|Business Segment|Please select|Name of Output|What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('Name of Requestor', r'Name of Requestor\s*:?\s*([^\n\r]+?)(?=\s*(?:Requestor[\']*s?\s*Email|Business Segment|Please select|Name of Output|What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('Requestor\'s Email Address', r'Requestor[\']*s?\s*Email Address\s*:?\s*([^\n\r]+?)(?=\s*(?:Business Segment|Please select|Name of Output|What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('Business Segment / Corporate Function', r'Business Segment\s*/?\s*Corporate Function\s*:?\s*([^\n\r]+?)(?=\s*(?:Please select|Name of Output|What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('Please select the type of output', r'Please select[^:]*type of output\s*:?\s*([^\n\r]+?)(?=\s*(?:Name of Output|What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('Name of Output', r'Name of Output\s*:?\s*([^\n\r]+?)(?=\s*(?:What is the scope|What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('What is the scope', r'What is the scope[^:]*:?\s*([^\n\r]+?)(?=\s*(?:What is the purpose|Name of Data Owner|Link to Data Owner|$))'),
            ('What is the purpose', r'What is the purpose[^:]*:?\s*([^\n\r]+?)(?=\s*(?:Name of Data Owner|Link to Data Owner|$))'),
            ('Name of Data Owner', r'Name of Data Owner\s*:?\s*([^\n\r]+?)(?=\s*(?:Link to Data Owner|$))'),
        ]
        
        # Process each field
        for field_name, pattern in field_patterns:
            match = re.search(pattern, clean_description, re.IGNORECASE | re.DOTALL)
            if match:
                # Extract value and clean it
                raw_value = match.group(1).strip()
                # Remove any extra whitespace
                clean_value = re.sub(r'\s+', ' ', raw_value).strip()
                fields[field_name] = clean_value
            else:
                fields[field_name] = ""
        
        # Special handling for Link to Data Owner Approval - use extracted URLs
        if link_urls:
            # Join multiple URLs with line breaks for Excel
            fields['Link to Data Owner Approval'] = '\n'.join(link_urls)
        else:
            fields['Link to Data Owner Approval'] = ""
        
        return fields
    
    def extract_data(self):
        """Extract data from all loaded XML files"""
        if not self.xml_files:
            messagebox.showwarning("No Files", 
                                  "Please load XML files first!")
            return
        
        self.extracted_data = []
        
        for xml_file in self.xml_files:
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                # Find all items (JIRA issues)
                for item in root.findall('.//item'):
                    record = {}
                    
                    # Extract basic fields
                    record['File'] = os.path.basename(xml_file)
                    record['Key'] = self.get_text(item, 'key')
                    record['Summary'] = self.get_text(item, 'summary')
                    record['Type'] = self.get_text(item, 'type')
                    record['Status'] = self.get_text(item, 'status')
                    record['Priority'] = self.get_text(item, 'priority')
                    record['Assignee'] = self.get_text(item, 'assignee')
                    record['Reporter'] = self.get_text(item, 'reporter')
                    record['Created'] = self.get_text(item, 'created')
                    record['Updated'] = self.get_text(item, 'updated')
                    
                    # Extract and parse description
                    description = self.get_text(item, 'description')
                    parsed_fields = self.parse_description_field(description)
                    
                    # Merge parsed fields
                    record.update(parsed_fields)
                    
                    # Store raw description as well
                    record['Raw Description'] = description
                    
                    self.extracted_data.append(record)
                    
            except Exception as e:
                messagebox.showerror("Error", 
                                   f"Error parsing {xml_file}:\n{str(e)}")
        
        if self.extracted_data:
            self.display_data()
            self.generate_analysis()
            self.status_label.config(
                text=f"Extracted {len(self.extracted_data)} record(s)",
                foreground="green"
            )
        else:
            messagebox.showwarning("No Data", 
                                  "No data could be extracted from the XML files.")
    
    def get_text(self, element, tag):
        """Safely get text from XML element"""
        child = element.find(tag)
        return child.text if child is not None and child.text else ""
    
    def display_data(self):
        """Display extracted data in treeview"""
        # Clear existing data
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if not self.extracted_data:
            return
        
        # Get columns (exclude raw description for display)
        columns = [k for k in self.extracted_data[0].keys() 
                  if k != 'Raw Description']
        
        self.tree['columns'] = columns
        self.tree['show'] = 'headings'
        
        # Configure columns
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150, minwidth=100)
        
        # Insert data
        for record in self.extracted_data:
            values = [record.get(col, "") for col in columns]
            self.tree.insert('', tk.END, values=values)
    
    def generate_analysis(self):
        """Generate summary analysis of the data"""
        self.analysis_text.delete(1.0, tk.END)
        
        if not self.extracted_data:
            return
        
        df = pd.DataFrame(self.extracted_data)
        
        analysis = "=" * 60 + "\n"
        analysis += "DATA SUMMARY\n"
        analysis += "=" * 60 + "\n\n"
        
        analysis += f"Total Records: {len(self.extracted_data)}\n"
        analysis += f"Total XML Files: {len(self.xml_files)}\n\n"
        
        # Status breakdown
        if 'Status' in df.columns:
            analysis += "\n--- Status Breakdown ---\n"
            status_counts = df['Status'].value_counts()
            for status, count in status_counts.items():
                analysis += f"  {status}: {count}\n"
        
        # Type breakdown
        if 'Type' in df.columns:
            analysis += "\n--- Issue Type Breakdown ---\n"
            type_counts = df['Type'].value_counts()
            for issue_type, count in type_counts.items():
                analysis += f"  {issue_type}: {count}\n"
        
        # Business Segment breakdown
        if 'Business Segment / Corporate Function' in df.columns:
            analysis += "\n--- Business Segment Breakdown ---\n"
            segment_counts = df['Business Segment / Corporate Function'].value_counts()
            for segment, count in segment_counts.items():
                if segment:
                    analysis += f"  {segment}: {count}\n"
        
        # Requestor breakdown
        if 'Name of Requestor' in df.columns:
            analysis += "\n--- Top Requestors ---\n"
            requestor_counts = df['Name of Requestor'].value_counts().head(10)
            for requestor, count in requestor_counts.items():
                if requestor:
                    analysis += f"  {requestor}: {count}\n"
        
        # Date range
        if 'Date of Request' in df.columns:
            analysis += "\n--- Date Range ---\n"
            dates = df['Date of Request'].dropna()
            if not dates.empty:
                analysis += f"  Earliest: {dates.min()}\n"
                analysis += f"  Latest: {dates.max()}\n"
        
        self.analysis_text.insert(1.0, analysis)
    
    def export_to_excel(self):
        """Export extracted data to Excel file"""
        if not self.extracted_data:
            messagebox.showwarning("No Data", 
                                  "Please extract data first!")
            return
        
        # Show column selection dialog
        selected_columns = self.show_column_selector()
        
        if not selected_columns:
            return  # User cancelled
        
        # Ask for filename
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialfile=f"JIRA_Extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        
        if filename:
            try:
                df = pd.DataFrame(self.extracted_data)
                
                # Filter to selected columns only
                df_export = df[selected_columns]
                
                # Create Excel writer
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    # Main data sheet
                    df_export.to_excel(writer, sheet_name='Extracted Data', index=False)
                    
                    # Get the worksheet to apply formatting
                    worksheet = writer.sheets['Extracted Data']
                    
                    # Find the column index for "Link to Data Owner Approval"
                    link_col_idx = None
                    if 'Link to Data Owner Approval' in selected_columns:
                        link_col_idx = selected_columns.index('Link to Data Owner Approval') + 1  # +1 for Excel 1-based indexing
                    
                    # Auto-adjust column widths and apply text wrapping
                    for idx, column in enumerate(worksheet.columns, 1):
                        max_length = 0
                        column_letter = column[0].column_letter
                        
                        # Apply text wrapping to all cells
                        for cell in column:
                            try:
                                # Enable text wrapping for cells with newlines
                                if cell.value and '\n' in str(cell.value):
                                    cell.alignment = cell.alignment.copy(wrapText=True)
                                
                                # Calculate max length
                                if cell.value:
                                    # For cells with line breaks, use the longest line
                                    if '\n' in str(cell.value):
                                        lines = str(cell.value).split('\n')
                                        cell_length = max(len(line) for line in lines)
                                    else:
                                        cell_length = len(str(cell.value))
                                    
                                    if cell_length > max_length:
                                        max_length = cell_length
                            except:
                                pass
                        
                        # Set column width (with special handling for link columns)
                        if idx == link_col_idx:
                            # Make link columns wider
                            adjusted_width = min(max_length + 2, 80)
                        else:
                            adjusted_width = min(max_length + 2, 50)
                        
                        worksheet.column_dimensions[column_letter].width = adjusted_width
                    
                    # Summary sheet
                    summary_data = {
                        'Metric': ['Total Records', 'Total Files', 'Columns Exported', 'Export Date'],
                        'Value': [len(self.extracted_data), 
                                len(self.xml_files),
                                len(selected_columns),
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
                    }
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                    
                    # Format summary sheet
                    summary_ws = writer.sheets['Summary']
                    for column in summary_ws.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 50)
                        summary_ws.column_dimensions[column_letter].width = adjusted_width
                
                messagebox.showinfo("Success", 
                                  f"Data exported successfully to:\n{filename}\n\nColumns exported: {len(selected_columns)}")
                self.status_label.config(
                    text=f"Exported {len(selected_columns)} columns to {os.path.basename(filename)}",
                    foreground="green"
                )
                
            except Exception as e:
                messagebox.showerror("Error", 
                                   f"Error exporting to Excel:\n{str(e)}")
    
    def show_column_selector(self):
        """Show dialog to select columns for export"""
        if not self.extracted_data:
            return None
        
        # Create dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Columns to Export")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Variables to store result
        selected_columns = []
        column_vars = {}
        
        # Get all available columns
        all_columns = list(self.extracted_data[0].keys())
        
        # Identify description fields (extracted from description)
        description_fields = [
            'Date of Request', 'Name of Requestor', 
            'Requestor\'s Email Address', 
            'Business Segment / Corporate Function',
            'Please select the type of output', 'Name of Output',
            'What is the scope', 'What is the purpose',
            'Name of Data Owner', 'Link to Data Owner Approval'
        ]
        
        # Main frame
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Select columns to include in Excel export:", 
                 font=("Arial", 11, "bold")).pack(pady=(0, 10))
        
        # Quick select buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        def select_description_only():
            for col in column_vars:
                if col in description_fields:
                    column_vars[col].set(True)
                else:
                    column_vars[col].set(False)
        
        def select_all():
            for var in column_vars.values():
                var.set(True)
        
        def deselect_all():
            for var in column_vars.values():
                var.set(False)
        
        ttk.Button(button_frame, text="Select Description Fields Only", 
                  command=select_description_only).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Select All", 
                  command=select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Deselect All", 
                  command=deselect_all).pack(side=tk.LEFT, padx=5)
        
        # Create scrollable frame for checkboxes
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Group columns
        ttk.Label(scrollable_frame, text="Description Fields (Extracted):", 
                 font=("Arial", 10, "bold"), foreground="blue").pack(anchor=tk.W, pady=(5, 2))
        
        for col in all_columns:
            if col in description_fields:
                var = tk.BooleanVar(value=True)  # Description fields selected by default
                column_vars[col] = var
                cb = ttk.Checkbutton(scrollable_frame, text=col, variable=var)
                cb.pack(anchor=tk.W, padx=20)
        
        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        ttk.Label(scrollable_frame, text="Standard JIRA Fields:", 
                 font=("Arial", 10, "bold"), foreground="green").pack(anchor=tk.W, pady=(5, 2))
        
        for col in all_columns:
            if col not in description_fields and col != 'Raw Description':
                var = tk.BooleanVar(value=False)  # JIRA fields unselected by default
                column_vars[col] = var
                cb = ttk.Checkbutton(scrollable_frame, text=col, variable=var)
                cb.pack(anchor=tk.W, padx=20)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_export():
            selected = [col for col, var in column_vars.items() if var.get()]
            if not selected:
                messagebox.showwarning("No Selection", 
                                      "Please select at least one column!")
                return
            selected_columns.extend(selected)
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        ttk.Button(bottom_frame, text="Export Selected", 
                  command=on_export).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="Cancel", 
                  command=on_cancel).pack(side=tk.RIGHT, padx=5)
        
        # Wait for dialog to close
        self.root.wait_window(dialog)
        
        return selected_columns if selected_columns else None
    
    def clear_all(self):
        """Clear all data and reset"""
        self.xml_files = []
        self.extracted_data = []
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.analysis_text.delete(1.0, tk.END)
        self.raw_text.delete(1.0, tk.END)
        
        self.status_label.config(text="Cleared all data", foreground="blue")

def main():
    root = tk.Tk()
    app = JiraXMLExtractor(root)
    root.mainloop()

if __name__ == "__main__":
    main()
