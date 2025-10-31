"""
Excel Data Quality Analysis Tool
A GUI application for analyzing EDMO Data Quality Control Evaluation Workbooks
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter
import os
from datetime import datetime
from pathlib import Path


class ExcelDQAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel Data Quality Analyzer")
        self.root.geometry("1200x800")
        self.root.configure(bg="#f0f0f0")
        
        # Variables
        self.file_paths = []
        self.results = []
        self.log_data = []
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the main user interface"""
        # Header
        header_frame = tk.Frame(self.root, bg="#2c3e50", height=80)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="📊 Excel Data Quality Analyzer",
            font=("Helvetica", 24, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(pady=20)
        
        # Main content frame
        content_frame = tk.Frame(self.root, bg="#f0f0f0")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # File selection section
        self.setup_file_section(content_frame)
        
        # Progress section
        self.setup_progress_section(content_frame)
        
        # Results section
        self.setup_results_section(content_frame)
        
        # Action buttons
        self.setup_action_buttons(content_frame)
        
    def setup_file_section(self, parent):
        """Setup file selection section"""
        file_frame = tk.LabelFrame(
            parent, 
            text="📁 File Selection",
            font=("Helvetica", 12, "bold"),
            bg="#f0f0f0",
            padx=10,
            pady=10
        )
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # File list
        self.file_listbox = tk.Listbox(
            file_frame,
            height=4,
            font=("Courier", 10),
            bg="white",
            selectmode=tk.EXTENDED
        )
        self.file_listbox.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons
        btn_frame = tk.Frame(file_frame, bg="#f0f0f0")
        btn_frame.pack(fill=tk.X)
        
        self.add_btn = tk.Button(
            btn_frame,
            text="➕ Add Files",
            command=self.add_files,
            font=("Helvetica", 10),
            bg="#3498db",
            fg="white",
            padx=20,
            pady=5,
            cursor="hand2"
        )
        self.add_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.remove_btn = tk.Button(
            btn_frame,
            text="➖ Remove Selected",
            command=self.remove_files,
            font=("Helvetica", 10),
            bg="#e74c3c",
            fg="white",
            padx=20,
            pady=5,
            cursor="hand2"
        )
        self.remove_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = tk.Button(
            btn_frame,
            text="🗑️ Clear All",
            command=self.clear_files,
            font=("Helvetica", 10),
            bg="#95a5a6",
            fg="white",
            padx=20,
            pady=5,
            cursor="hand2"
        )
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
    def setup_progress_section(self, parent):
        """Setup progress section"""
        progress_frame = tk.LabelFrame(
            parent,
            text="⚙️ Analysis Progress",
            font=("Helvetica", 12, "bold"),
            bg="#f0f0f0",
            padx=10,
            pady=10
        )
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = tk.Label(
            progress_frame,
            text="Ready to analyze files...",
            font=("Helvetica", 10),
            bg="#f0f0f0",
            fg="#2c3e50"
        )
        self.progress_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='determinate',
            length=100
        )
        self.progress_bar.pack(fill=tk.X)
        
    def setup_results_section(self, parent):
        """Setup results display section"""
        results_frame = tk.LabelFrame(
            parent,
            text="📋 Analysis Results",
            font=("Helvetica", 12, "bold"),
            bg="#f0f0f0",
            padx=10,
            pady=10
        )
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(results_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Summary tab
        summary_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(summary_frame, text="Summary")
        
        self.summary_text = scrolledtext.ScrolledText(
            summary_frame,
            wrap=tk.WORD,
            font=("Courier", 10),
            bg="white",
            padx=10,
            pady=10
        )
        self.summary_text.pack(fill=tk.BOTH, expand=True)
        
        # Detailed log tab
        log_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(log_frame, text="Detailed Log")
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="white",
            padx=10,
            pady=10
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def setup_action_buttons(self, parent):
        """Setup action buttons"""
        action_frame = tk.Frame(parent, bg="#f0f0f0")
        action_frame.pack(fill=tk.X)
        
        self.analyze_btn = tk.Button(
            action_frame,
            text="🚀 Start Analysis",
            command=self.start_analysis,
            font=("Helvetica", 12, "bold"),
            bg="#27ae60",
            fg="white",
            padx=30,
            pady=10,
            cursor="hand2"
        )
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.export_btn = tk.Button(
            action_frame,
            text="💾 Export Results",
            command=self.export_results,
            font=("Helvetica", 12, "bold"),
            bg="#f39c12",
            fg="white",
            padx=30,
            pady=10,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.export_btn.pack(side=tk.LEFT)
        
    def add_files(self):
        """Add files to the list"""
        files = filedialog.askopenfilenames(
            title="Select Excel Files",
            filetypes=[("Excel Files", "*.xlsx *.xlsm *.xls"), ("All Files", "*.*")]
        )
        
        for file in files:
            if file not in self.file_paths:
                self.file_paths.append(file)
                self.file_listbox.insert(tk.END, os.path.basename(file))
                
    def remove_files(self):
        """Remove selected files"""
        selected = self.file_listbox.curselection()
        for index in reversed(selected):
            self.file_listbox.delete(index)
            self.file_paths.pop(index)
            
    def clear_files(self):
        """Clear all files"""
        self.file_listbox.delete(0, tk.END)
        self.file_paths.clear()
        
    def start_analysis(self):
        """Start the analysis process"""
        if not self.file_paths:
            messagebox.showwarning("No Files", "Please add at least one file to analyze.")
            return
            
        # Clear previous results
        self.results.clear()
        self.log_data.clear()
        self.summary_text.delete(1.0, tk.END)
        self.log_text.delete(1.0, tk.END)
        
        # Disable buttons
        self.analyze_btn.config(state=tk.DISABLED)
        self.export_btn.config(state=tk.DISABLED)
        
        # Reset progress
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(self.file_paths)
        
        # Process each file
        for idx, file_path in enumerate(self.file_paths):
            self.progress_label.config(text=f"Analyzing: {os.path.basename(file_path)}")
            self.root.update()
            
            try:
                self.analyze_file(file_path)
            except Exception as e:
                self.log_message(f"ERROR processing {os.path.basename(file_path)}: {str(e)}", "ERROR")
                
            self.progress_bar['value'] = idx + 1
            self.root.update()
            
        # Analysis complete
        self.progress_label.config(text="✅ Analysis Complete!")
        self.display_summary()
        self.analyze_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        
        messagebox.showinfo("Complete", "Analysis completed successfully!")
        
    def analyze_file(self, file_path):
        """Analyze a single Excel file"""
        self.log_message(f"\n{'='*80}\nAnalyzing File: {os.path.basename(file_path)}\n{'='*80}", "INFO")
        
        # Load workbook
        wb = openpyxl.load_workbook(file_path, data_only=False)
        
        # Check for required sheets
        if "DQ Controls Evaluation Sheet" not in wb.sheetnames:
            self.log_message("ERROR: 'DQ Controls Evaluation Sheet' not found!", "ERROR")
            return
            
        if "DQ Control Scoping" not in wb.sheetnames:
            self.log_message("ERROR: 'DQ Control Scoping' not found!", "ERROR")
            return
            
        # Analyze DQ Controls Evaluation Sheet
        eval_sheet = wb["DQ Controls Evaluation Sheet"]
        self.analyze_evaluation_sheet(eval_sheet, file_path)
        
        # Analyze DQ Control Scoping Sheet
        scoping_sheet = wb["DQ Control Scoping"]
        self.analyze_scoping_sheet(scoping_sheet, file_path)
        
        # Cross-reference check
        self.cross_reference_check(eval_sheet, scoping_sheet, file_path)
        
        wb.close()
        
    def find_header_row(self, sheet, header_keywords):
        """Find the header row based on keywords"""
        for row_idx in range(1, min(50, sheet.max_row + 1)):
            row_values = [str(cell.value).strip() if cell.value else "" for cell in sheet[row_idx]]
            row_text = " ".join(row_values).upper()
            
            # Check if all keywords are present
            if all(keyword.upper() in row_text for keyword in header_keywords):
                return row_idx
        return None
        
    def analyze_evaluation_sheet(self, sheet, file_path):
        """Analyze the DQ Controls Evaluation Sheet"""
        self.log_message("\n--- DQ Controls Evaluation Sheet Analysis ---", "INFO")
        
        # Find header row
        header_keywords = ["MAL", "EUC CODE", "DATABASE NAME", "DQ EVALUATION UNIQUE IDENTIFIER"]
        header_row = self.find_header_row(sheet, header_keywords)
        
        if not header_row:
            self.log_message("ERROR: Could not find header row in Evaluation Sheet", "ERROR")
            return
            
        self.log_message(f"Header row found at: Row {header_row}", "INFO")
        
        # Find Column D
        col_d_idx = 4  # Column D is the 4th column
        
        # Analyze each row
        passed = 0
        failed = 0
        
        for row_idx in range(header_row + 1, sheet.max_row + 1):
            cell = sheet.cell(row=row_idx, column=col_d_idx)
            cell_value = cell.value
            
            if not cell_value:
                continue
                
            # Check 1: Is it a formula?
            is_formula = str(cell_value).startswith('=')
            formula_check = "PASSED" if is_formula else "FAILED"
            
            # Get the actual value (for formulas, we need to evaluate)
            if is_formula:
                # For formulas, we'll use data_only workbook
                actual_value = str(cell_value)
            else:
                actual_value = str(cell_value)
                
            # Check 2: Does it have 5 components?
            components = actual_value.replace('=', '').strip().split('.')
            component_check = "PASSED" if len(components) == 5 else "FAILED"
            
            # Log the result
            result = {
                "File": os.path.basename(file_path),
                "Sheet": "DQ Controls Evaluation Sheet",
                "Row": row_idx,
                "Cell": f"D{row_idx}",
                "Value": actual_value[:50],
                "Formula Check": formula_check,
                "Component Check": component_check,
                "Components": len(components)
            }
            
            self.log_data.append(result)
            
            if formula_check == "PASSED" and component_check == "PASSED":
                passed += 1
            else:
                failed += 1
                
            self.log_message(
                f"Row {row_idx}: Formula Check = {formula_check}, Component Check = {component_check} ({len(components)} components)",
                "WARNING" if formula_check == "FAILED" or component_check == "FAILED" else "INFO"
            )
            
        self.log_message(f"\nEvaluation Sheet Summary: {passed} PASSED, {failed} FAILED", "INFO")
        
    def analyze_scoping_sheet(self, sheet, file_path):
        """Analyze the DQ Control Scoping Sheet"""
        self.log_message("\n--- DQ Control Scoping Sheet Analysis ---", "INFO")
        
        # Start from row 10 or find header
        start_row = 10
        header_keywords = ["UNIQUE IDENTIFIERS IN SCOPE"]
        header_row = self.find_header_row(sheet, header_keywords)
        
        if header_row:
            start_row = header_row + 1
            
        self.log_message(f"Starting analysis from row: {start_row}", "INFO")
        
        # Check columns AF-AV for formulas (columns 32-48)
        af_col = 32  # Column AF
        av_col = 48  # Column AV
        
        passed = 0
        failed = 0
        
        for row_idx in range(start_row, min(start_row + 100, sheet.max_row + 1)):
            row_has_data = False
            row_results = []
            
            for col_idx in range(af_col, av_col + 1):
                cell = sheet.cell(row=row_idx, column=col_idx)
                cell_value = cell.value
                
                if cell_value:
                    row_has_data = True
                    is_formula = str(cell_value).startswith('=')
                    formula_check = "PASSED" if is_formula else "FAILED"
                    
                    col_letter = get_column_letter(col_idx)
                    row_results.append({
                        "Column": col_letter,
                        "Formula Check": formula_check
                    })
                    
                    if formula_check == "PASSED":
                        passed += 1
                    else:
                        failed += 1
                        
            if row_has_data and row_results:
                result_summary = ", ".join([f"{r['Column']}: {r['Formula Check']}" for r in row_results[:3]])
                if len(row_results) > 3:
                    result_summary += f" ... ({len(row_results)} total columns)"
                self.log_message(f"Row {row_idx}: {result_summary}", "INFO")
                
        self.log_message(f"\nScoping Sheet Formula Check Summary: {passed} PASSED, {failed} FAILED", "INFO")
        
    def cross_reference_check(self, eval_sheet, scoping_sheet, file_path):
        """Cross-reference between Evaluation and Scoping sheets"""
        self.log_message("\n--- Cross-Reference Analysis ---", "INFO")
        
        # Find headers
        eval_header_row = self.find_header_row(eval_sheet, ["MAL", "DATABASE NAME"])
        scoping_header_row = 10  # or find it dynamically
        
        if not eval_header_row:
            self.log_message("ERROR: Could not find evaluation sheet header", "ERROR")
            return
            
        # Load scoping data (columns Z-AD are columns 26-30)
        scoping_data = []
        for row_idx in range(scoping_header_row, min(scoping_header_row + 500, scoping_sheet.max_row + 1)):
            row_data = {
                "System": str(scoping_sheet.cell(row=row_idx, column=26).value or "").strip().upper(),
                "Database": str(scoping_sheet.cell(row=row_idx, column=27).value or "").strip().upper(),
                "Schema": str(scoping_sheet.cell(row=row_idx, column=28).value or "").strip().upper(),
                "Table": str(scoping_sheet.cell(row=row_idx, column=29).value or "").strip().upper(),
                "Column": str(scoping_sheet.cell(row=row_idx, column=30).value or "").strip().upper()
            }
            
            if any(row_data.values()):
                scoping_data.append(row_data)
                
        self.log_message(f"Loaded {len(scoping_data)} scoping records", "INFO")
        
        # Check each evaluation row
        matched = 0
        unmatched = 0
        
        for row_idx in range(eval_header_row + 1, min(eval_header_row + 500, eval_sheet.max_row + 1)):
            cell = eval_sheet.cell(row=row_idx, column=4)  # Column D
            cell_value = str(cell.value or "").replace('=', '').strip()
            
            if not cell_value or cell_value == "None":
                continue
                
            components = cell_value.split('.')
            if len(components) != 5:
                continue
                
            # Normalize components
            comp_system = components[0].strip().upper()
            comp_database = components[1].strip().upper()
            comp_schema = components[2].strip().upper()
            comp_table = components[3].strip().upper()
            comp_column = components[4].strip().upper()
            
            # Try to find match
            match_found = False
            for scoping_row in scoping_data:
                if (scoping_row["System"] == comp_system and
                    scoping_row["Database"] == comp_database and
                    scoping_row["Schema"] == comp_schema and
                    scoping_row["Table"] == comp_table and
                    scoping_row["Column"] == comp_column):
                    match_found = True
                    break
                    
            if match_found:
                matched += 1
                self.log_message(f"Row {row_idx}: ✓ MATCH FOUND - {cell_value[:50]}", "INFO")
            else:
                unmatched += 1
                self.log_message(f"Row {row_idx}: ✗ NO MATCH - {cell_value[:50]}", "WARNING")
                self.log_message(f"  Components: {comp_system} | {comp_database} | {comp_schema} | {comp_table} | {comp_column}", "WARNING")
                
        self.log_message(f"\nCross-Reference Summary: {matched} MATCHED, {unmatched} UNMATCHED", "INFO")
        
    def log_message(self, message, level="INFO"):
        """Add a message to the log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.insert(tk.END, formatted_msg)
        
        # Color coding
        if level == "ERROR":
            self.log_text.tag_add("error", "end-2l", "end-1l")
            self.log_text.tag_config("error", foreground="red")
        elif level == "WARNING":
            self.log_text.tag_add("warning", "end-2l", "end-1l")
            self.log_text.tag_config("warning", foreground="orange")
        elif level == "INFO":
            self.log_text.tag_add("info", "end-2l", "end-1l")
            self.log_text.tag_config("info", foreground="blue")
            
        self.log_text.see(tk.END)
        self.root.update()
        
    def display_summary(self):
        """Display summary of results"""
        summary = f"""
╔═══════════════════════════════════════════════════════════════╗
║                    ANALYSIS SUMMARY                           ║
╚═══════════════════════════════════════════════════════════════╝

Files Analyzed: {len(self.file_paths)}
Total Records: {len(self.log_data)}

Analysis Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Results saved and ready for export.

"""
        self.summary_text.insert(tk.END, summary)
        
    def export_results(self):
        """Export results to Excel"""
        if not self.log_data:
            messagebox.showwarning("No Data", "No analysis data to export.")
            return
            
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            initialfile=f"DQ_Analysis_Results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        
        if not file_path:
            return
            
        try:
            # Create DataFrame and export
            df = pd.DataFrame(self.log_data)
            
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Analysis Results', index=False)
                
                # Also export the log
                log_content = self.log_text.get(1.0, tk.END)
                log_df = pd.DataFrame({'Log': [log_content]})
                log_df.to_excel(writer, sheet_name='Detailed Log', index=False)
                
            messagebox.showinfo("Success", f"Results exported successfully to:\n{file_path}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export results:\n{str(e)}")


def main():
    """Main function to run the application"""
    root = tk.Tk()
    app = ExcelDQAnalyzer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
