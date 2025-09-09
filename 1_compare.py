import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import pandas as pd
from pathlib import Path
import re
from datetime import datetime
from collections import defaultdict
import threading

class JiraProjectComparator:
    def __init__(self, root):
        self.root = root
        self.root.title("Jira Project Fields Comparator")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')
        
        # Variables
        self.project1_data = None
        self.project2_data = None
        self.project1_path = tk.StringVar()
        self.project2_path = tk.StringVar()
        self.comparison_result = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Jira Project Fields Comparator", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # File selection section
        files_frame = ttk.LabelFrame(main_frame, text="Select Project Files", padding="10")
        files_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        files_frame.columnconfigure(1, weight=1)
        
        # Project 1
        ttk.Label(files_frame, text="Project 1:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Entry(files_frame, textvariable=self.project1_path, state="readonly").grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        ttk.Button(files_frame, text="Browse", 
                  command=lambda: self.browse_file(self.project1_path, "Project 1")).grid(
            row=0, column=2)
        
        # Project 2
        ttk.Label(files_frame, text="Project 2:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        ttk.Entry(files_frame, textvariable=self.project2_path, state="readonly").grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 10), pady=(10, 0))
        ttk.Button(files_frame, text="Browse", 
                  command=lambda: self.browse_file(self.project2_path, "Project 2")).grid(
            row=1, column=2, pady=(10, 0))
        
        # Control buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        self.compare_btn = ttk.Button(control_frame, text="Compare Projects", 
                                     command=self.compare_projects, style="Accent.TButton")
        self.compare_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.export_btn = ttk.Button(control_frame, text="Export to Excel", 
                                    command=self.export_to_excel, state="disabled")
        self.export_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(control_frame, text="Clear Results", 
                  command=self.clear_results).pack(side=tk.LEFT)
        
        # Results section
        results_frame = ttk.LabelFrame(main_frame, text="Comparison Results", padding="10")
        results_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Create notebook for different views
        self.notebook = ttk.Notebook(results_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Summary tab
        self.summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.summary_frame, text="Summary")
        
        self.summary_text = scrolledtext.ScrolledText(self.summary_frame, wrap=tk.WORD, 
                                                     height=20, font=("Consolas", 10))
        self.summary_text.pack(fill=tk.BOTH, expand=True)
        
        # Detailed comparison tab
        self.details_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.details_frame, text="Detailed Analysis")
        
        self.details_text = scrolledtext.ScrolledText(self.details_frame, wrap=tk.WORD, 
                                                     height=20, font=("Consolas", 9))
        self.details_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
    
    def browse_file(self, path_var, project_name):
        """Browse and select a file"""
        file_path = filedialog.askopenfilename(
            title=f"Select {project_name} file",
            filetypes=[
                ("All supported", "*.json;*.txt;*.csv"),
                ("JSON files", "*.json"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            path_var.set(file_path)
            self.status_var.set(f"Selected {project_name}: {Path(file_path).name}")
    
    def parse_file_content(self, file_path):
        """Parse file content and extract Jira project data"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Try to parse as JSON first
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
            
            # Try to extract JSON from text content
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # If it looks like CSV, try to parse it
            if ',' in content and '\n' in content:
                lines = content.split('\n')
                # Simple CSV parsing for field mapping
                data = {"Fields": {}}
                for line in lines[1:]:  # Skip header
                    if line.strip():
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 2:
                            data["Fields"][parts[0]] = parts[1]
                return data
            
            raise ValueError("Unable to parse file format")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error reading file {file_path}: {str(e)}")
            return None
    
    def extract_project_info(self, data):
        """Extract project information from parsed data"""
        project_info = {
            'name': '',
            'issue_types': set(),
            'fields': {},
            'custom_fields': {},
            'standard_fields': {}
        }
        
        if not data or "Fields" not in data:
            return project_info
        
        fields = data["Fields"]
        
        # Extract project name
        if "project" in fields and isinstance(fields["project"], dict):
            project_info['name'] = fields["project"].get("key", "Unknown")
        
        # Categorize fields
        for field_id, field_data in fields.items():
            if isinstance(field_data, dict):
                field_name = field_data.get("name", field_id)
            else:
                field_name = str(field_data)
            
            # Identify issue types
            if field_id == "issuetype" and isinstance(field_data, dict):
                project_info['issue_types'].add(field_data.get("name", "Unknown"))
            
            # Categorize fields
            if field_id.startswith("customfield_"):
                project_info['custom_fields'][field_id] = field_name
            else:
                project_info['standard_fields'][field_id] = field_name
            
            project_info['fields'][field_id] = field_name
        
        return project_info
    
    def compare_projects(self):
        """Compare two projects and generate analysis"""
        if not self.project1_path.get() or not self.project2_path.get():
            messagebox.showwarning("Warning", "Please select both project files")
            return
        
        def do_comparison():
            try:
                self.progress.start()
                self.status_var.set("Loading and parsing files...")
                
                # Parse files
                self.project1_data = self.parse_file_content(self.project1_path.get())
                self.project2_data = self.parse_file_content(self.project2_path.get())
                
                if not self.project1_data or not self.project2_data:
                    return
                
                self.status_var.set("Extracting project information...")
                
                # Extract project info
                proj1_info = self.extract_project_info(self.project1_data)
                proj2_info = self.extract_project_info(self.project2_data)
                
                self.status_var.set("Performing comparison...")
                
                # Perform comparison
                self.comparison_result = self.perform_detailed_comparison(proj1_info, proj2_info)
                
                # Update UI
                self.root.after(0, self.update_results_ui)
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Comparison failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self.progress.stop())
                self.root.after(0, lambda: self.status_var.set("Comparison completed"))
        
        # Run in separate thread to prevent UI freezing
        threading.Thread(target=do_comparison, daemon=True).start()
    
    def perform_detailed_comparison(self, proj1, proj2):
        """Perform detailed comparison between two projects"""
        result = {
            'project1_name': proj1['name'] or Path(self.project1_path.get()).stem,
            'project2_name': proj2['name'] or Path(self.project2_path.get()).stem,
            'summary': {},
            'detailed_analysis': {}
        }
        
        # Summary statistics
        result['summary'] = {
            'project1_total_fields': len(proj1['fields']),
            'project2_total_fields': len(proj2['fields']),
            'project1_custom_fields': len(proj1['custom_fields']),
            'project2_custom_fields': len(proj2['custom_fields']),
            'project1_standard_fields': len(proj1['standard_fields']),
            'project2_standard_fields': len(proj2['standard_fields']),
            'common_fields': len(set(proj1['fields'].keys()) & set(proj2['fields'].keys())),
            'project1_unique_fields': len(set(proj1['fields'].keys()) - set(proj2['fields'].keys())),
            'project2_unique_fields': len(set(proj2['fields'].keys()) - set(proj1['fields'].keys()))
        }
        
        # Detailed analysis
        all_field_ids = set(proj1['fields'].keys()) | set(proj2['fields'].keys())
        
        result['detailed_analysis'] = {
            'common_fields': {},
            'project1_unique': {},
            'project2_unique': {},
            'different_names': {}
        }
        
        for field_id in all_field_ids:
            proj1_has = field_id in proj1['fields']
            proj2_has = field_id in proj2['fields']
            
            if proj1_has and proj2_has:
                proj1_name = proj1['fields'][field_id]
                proj2_name = proj2['fields'][field_id]
                
                if proj1_name == proj2_name:
                    result['detailed_analysis']['common_fields'][field_id] = proj1_name
                else:
                    result['detailed_analysis']['different_names'][field_id] = {
                        'project1': proj1_name,
                        'project2': proj2_name
                    }
            elif proj1_has:
                result['detailed_analysis']['project1_unique'][field_id] = proj1['fields'][field_id]
            else:
                result['detailed_analysis']['project2_unique'][field_id] = proj2['fields'][field_id]
        
        return result
    
    def update_results_ui(self):
        """Update the results UI with comparison data"""
        if not self.comparison_result:
            return
        
        # Update summary
        self.summary_text.delete('1.0', tk.END)
        summary_text = self.generate_summary_report()
        self.summary_text.insert('1.0', summary_text)
        
        # Update detailed analysis
        self.details_text.delete('1.0', tk.END)
        details_text = self.generate_detailed_report()
        self.details_text.insert('1.0', details_text)
        
        # Enable export button
        self.export_btn.config(state="normal")
    
    def generate_summary_report(self):
        """Generate summary report text"""
        if not self.comparison_result:
            return "No comparison data available"
        
        result = self.comparison_result
        summary = result['summary']
        
        report = f"""
JIRA PROJECT FIELDS COMPARISON SUMMARY
{'='*50}

Project 1: {result['project1_name']}
Project 2: {result['project2_name']}
Comparison Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

OVERVIEW
--------
• Project 1 Total Fields: {summary['project1_total_fields']}
• Project 2 Total Fields: {summary['project2_total_fields']}

FIELD BREAKDOWN
---------------
Project 1:
  • Custom Fields: {summary['project1_custom_fields']}
  • Standard Fields: {summary['project1_standard_fields']}

Project 2:
  • Custom Fields: {summary['project2_custom_fields']}
  • Standard Fields: {summary['project2_standard_fields']}

COMPARISON RESULTS
------------------
• Common Fields: {summary['common_fields']} ({summary['common_fields']/max(summary['project1_total_fields'], summary['project2_total_fields'])*100:.1f}% similarity)
• {result['project1_name']} Unique Fields: {summary['project1_unique_fields']}
• {result['project2_name']} Unique Fields: {summary['project2_unique_fields']}

RECOMMENDATIONS
---------------
"""
        
        # Add recommendations based on analysis
        if summary['project1_unique_fields'] > 0:
            report += f"• Consider migrating {summary['project1_unique_fields']} unique fields from {result['project1_name']} to {result['project2_name']}\n"
        
        if summary['project2_unique_fields'] > 0:
            report += f"• Consider migrating {summary['project2_unique_fields']} unique fields from {result['project2_name']} to {result['project1_name']}\n"
        
        similarity_pct = summary['common_fields']/max(summary['project1_total_fields'], summary['project2_total_fields'])*100
        if similarity_pct < 50:
            report += "• Low field similarity detected - consider field standardization across projects\n"
        elif similarity_pct > 80:
            report += "• High field similarity - projects are well aligned\n"
        
        return report
    
    def generate_detailed_report(self):
        """Generate detailed analysis report"""
        if not self.comparison_result:
            return "No comparison data available"
        
        result = self.comparison_result
        analysis = result['detailed_analysis']
        
        report = f"""
DETAILED FIELD ANALYSIS
{'='*50}

COMMON FIELDS ({len(analysis['common_fields'])})
{'-'*20}
"""
        
        for field_id, field_name in sorted(analysis['common_fields'].items()):
            field_type = "Custom" if field_id.startswith("customfield_") else "Standard"
            report += f"• {field_id}: {field_name} ({field_type})\n"
        
        report += f"""

{result['project1_name'].upper()} UNIQUE FIELDS ({len(analysis['project1_unique'])})
{'-'*30}
"""
        
        for field_id, field_name in sorted(analysis['project1_unique'].items()):
            field_type = "Custom" if field_id.startswith("customfield_") else "Standard"
            report += f"• {field_id}: {field_name} ({field_type})\n"
        
        report += f"""

{result['project2_name'].upper()} UNIQUE FIELDS ({len(analysis['project2_unique'])})
{'-'*30}
"""
        
        for field_id, field_name in sorted(analysis['project2_unique'].items()):
            field_type = "Custom" if field_id.startswith("customfield_") else "Standard"
            report += f"• {field_id}: {field_name} ({field_type})\n"
        
        if analysis['different_names']:
            report += f"""

FIELDS WITH DIFFERENT NAMES ({len(analysis['different_names'])})
{'-'*35}
"""
            for field_id, names in sorted(analysis['different_names'].items()):
                field_type = "Custom" if field_id.startswith("customfield_") else "Standard"
                report += f"• {field_id} ({field_type}):\n"
                report += f"  - {result['project1_name']}: {names['project1']}\n"
                report += f"  - {result['project2_name']}: {names['project2']}\n"
        
        return report
    
    def export_to_excel(self):
        """Export comparison results to Excel"""
        if not self.comparison_result:
            messagebox.showwarning("Warning", "No comparison data to export")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Save Excel Report",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            self.status_var.set("Exporting to Excel...")
            
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Summary sheet
                summary_data = []
                for key, value in self.comparison_result['summary'].items():
                    summary_data.append([key.replace('_', ' ').title(), value])
                
                summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Value'])
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Common fields sheet
                if self.comparison_result['detailed_analysis']['common_fields']:
                    common_data = []
                    for field_id, field_name in self.comparison_result['detailed_analysis']['common_fields'].items():
                        common_data.append([
                            field_id, 
                            field_name, 
                            "Custom" if field_id.startswith("customfield_") else "Standard"
                        ])
                    
                    common_df = pd.DataFrame(common_data, columns=['Field ID', 'Field Name', 'Type'])
                    common_df.to_excel(writer, sheet_name='Common Fields', index=False)
                
                # Project 1 unique fields
                if self.comparison_result['detailed_analysis']['project1_unique']:
                    proj1_data = []
                    for field_id, field_name in self.comparison_result['detailed_analysis']['project1_unique'].items():
                        proj1_data.append([
                            field_id, 
                            field_name, 
                            "Custom" if field_id.startswith("customfield_") else "Standard"
                        ])
                    
                    proj1_df = pd.DataFrame(proj1_data, columns=['Field ID', 'Field Name', 'Type'])
                    proj1_df.to_excel(writer, sheet_name=f'{self.comparison_result["project1_name"]} Unique', index=False)
                
                # Project 2 unique fields
                if self.comparison_result['detailed_analysis']['project2_unique']:
                    proj2_data = []
                    for field_id, field_name in self.comparison_result['detailed_analysis']['project2_unique'].items():
                        proj2_data.append([
                            field_id, 
                            field_name, 
                            "Custom" if field_id.startswith("customfield_") else "Standard"
                        ])
                    
                    proj2_df = pd.DataFrame(proj2_data, columns=['Field ID', 'Field Name', 'Type'])
                    proj2_df.to_excel(writer, sheet_name=f'{self.comparison_result["project2_name"]} Unique', index=False)
                
                # Different names sheet
                if self.comparison_result['detailed_analysis']['different_names']:
                    diff_data = []
                    for field_id, names in self.comparison_result['detailed_analysis']['different_names'].items():
                        diff_data.append([
                            field_id,
                            names['project1'],
                            names['project2'],
                            "Custom" if field_id.startswith("customfield_") else "Standard"
                        ])
                    
                    diff_df = pd.DataFrame(diff_data, columns=[
                        'Field ID', 
                        f'{self.comparison_result["project1_name"]} Name',
                        f'{self.comparison_result["project2_name"]} Name',
                        'Type'
                    ])
                    diff_df.to_excel(writer, sheet_name='Different Names', index=False)
            
            self.status_var.set(f"Report exported successfully: {Path(file_path).name}")
            messagebox.showinfo("Success", f"Report exported successfully to:\n{file_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
            self.status_var.set("Export failed")
    
    def clear_results(self):
        """Clear all results and reset the interface"""
        self.project1_data = None
        self.project2_data = None
        self.comparison_result = None
        self.project1_path.set("")
        self.project2_path.set("")
        
        self.summary_text.delete('1.0', tk.END)
        self.details_text.delete('1.0', tk.END)
        
        self.export_btn.config(state="disabled")
        self.status_var.set("Ready")


def main():
    root = tk.Tk()
    
    # Set up styles
    style = ttk.Style()
    style.theme_use('clam')
    
    app = JiraProjectComparator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
