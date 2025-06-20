import os
import re
import xml.etree.ElementTree as ET
import glob
import pandas as pd
from docx import Document
from docx.shared import Inches
import matplotlib.pyplot as plt
from PIL import Image, ImageGrab
import logging
from datetime import datetime
import sys
from pathlib import Path

# Try to import optional PDF conversion library
try:
    from docx2pdf import convert
    PDF_AVAILABLE = True
    print("PDF conversion available via docx2pdf")
except ImportError:
    PDF_AVAILABLE = False
    print("PDF conversion not available. Install docx2pdf if you need PDF output: pip install docx2pdf")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='alteryx_workflow_documentation.log'
)

class AlteryxWorkflowDocumenter:
    """Class to document Alteryx workflows"""
    
    def __init__(self, workflow_dir="C:\\Users\\framework"):
        """Initialize the documenter with the directory containing workflow files"""
        self.workflow_dir = workflow_dir
        self.doc = Document()
        self.workflows = []
        self.component_descriptions = {
            "Input": "Data source input connection",
            "Filter": "Filters data based on specified conditions",
            "Formula": "Applies formulas to create or modify fields",
            "Join": "Combines multiple datasets together",
            "Union": "Combines datasets by appending rows",
            "Output": "Exports data to specified location",
            "Sort": "Arranges data in specified order",
            "Summarize": "Aggregates data using grouping functions",
            "TextInput": "Static text data input",
            "TextToColumns": "Splits text fields into multiple columns",
            "Select": "Selects, renames, or reorders fields",
            "Comment": "Contains workflow documentation notes",
            "Browse": "Displays data for review during workflow development",
            "Sample": "Creates a sample of the data"
            # Add more component descriptions as needed
        }
        logging.info(f"Initialized AlteryxWorkflowDocumenter with directory: {workflow_dir}")
    
    def find_workflow_files(self):
        """Find all Alteryx workflow files in the specified directory"""
        print(f"Looking for workflow files in: {self.workflow_dir}")
        
        # Check if directory exists
        if not os.path.exists(self.workflow_dir):
            print(f"ERROR: Directory {self.workflow_dir} does not exist!")
            logging.error(f"Directory {self.workflow_dir} does not exist")
            return []
        
        # List all files in the directory for debugging
        try:
            all_files = os.listdir(self.workflow_dir)
            print(f"All files in directory: {all_files}")
        except Exception as e:
            print(f"Error listing directory contents: {e}")
            return []
        
        # Look for .yxmd files
        workflow_pattern = os.path.join(self.workflow_dir, "*.yxmd")
        yxmd_files = glob.glob(workflow_pattern)
        print(f"Found .yxmd files: {yxmd_files}")
        
        # Also look for .bak files (backup Alteryx files)
        backup_pattern = os.path.join(self.workflow_dir, "*.bak")
        bak_files = glob.glob(backup_pattern)
        print(f"Found .bak files: {bak_files}")
        
        # Combine both types
        self.workflows = yxmd_files + bak_files
        
        print(f"Total workflow files found: {len(self.workflows)}")
        logging.info(f"Found {len(self.workflows)} workflow files")
        
        return self.workflows
    
    def parse_workflow(self, workflow_path):
        """Parse an Alteryx workflow file and extract component information"""
        try:
            print(f"Parsing workflow: {workflow_path}")
            tree = ET.parse(workflow_path)
            root = tree.getroot()
            
            # Extract workflow metadata
            workflow_name = os.path.basename(workflow_path)
            workflow_info = {
                'name': workflow_name,
                'path': workflow_path,
                'components': []
            }
            
            # Extract components (nodes)
            nodes = root.findall(".//Node")
            print(f"Found {len(nodes)} nodes in workflow")
            
            for node in nodes:
                component = {
                    'type': node.get('ToolID', ''),
                    'plugin': node.get('Plugin', ''),
                    'id': node.get('ToolID', ''),
                    'label': '',
                    'description': '',
                    'inputs': [],
                    'outputs': [],
                    'properties': {}
                }
                
                # Extract component label/description
                gui_settings = node.find(".//GuiSettings")
                if gui_settings is not None:
                    component['label'] = gui_settings.get('Html', '')
                
                # Extract properties
                properties = node.findall(".//Properties/Configuration/*")
                for prop in properties:
                    component['properties'][prop.tag] = prop.text
                
                # Extract connections (inputs and outputs)
                connections = root.findall(f".//Connection[@TargetID='{component['id']}']")
                for conn in connections:
                    component['inputs'].append({
                        'source_id': conn.get('SourceID', ''),
                        'source_type': '',  # To be filled later
                        'name': conn.get('Name', '')
                    })
                
                connections = root.findall(f".//Connection[@SourceID='{component['id']}']")
                for conn in connections:
                    component['outputs'].append({
                        'target_id': conn.get('TargetID', ''),
                        'target_type': '',  # To be filled later
                        'name': conn.get('Name', '')
                    })
                
                # Get component description
                component_type = component['plugin'].split('.')[-1] if '.' in component['plugin'] else component['plugin']
                component['description'] = self.component_descriptions.get(component_type, f"Component of type {component_type}")
                
                workflow_info['components'].append(component)
            
            # Fill in source/target types
            component_dict = {comp['id']: comp for comp in workflow_info['components']}
            for component in workflow_info['components']:
                for input_conn in component['inputs']:
                    if input_conn['source_id'] in component_dict:
                        source_comp = component_dict[input_conn['source_id']]
                        source_type = source_comp['plugin'].split('.')[-1] if '.' in source_comp['plugin'] else source_comp['plugin']
                        input_conn['source_type'] = source_type
                
                for output_conn in component['outputs']:
                    if output_conn['target_id'] in component_dict:
                        target_comp = component_dict[output_conn['target_id']]
                        target_type = target_comp['plugin'].split('.')[-1] if '.' in target_comp['plugin'] else target_comp['plugin']
                        output_conn['target_type'] = target_type
            
            logging.info(f"Successfully parsed workflow: {workflow_name}")
            return workflow_info
        except Exception as e:
            print(f"Error parsing workflow {workflow_path}: {str(e)}")
            logging.error(f"Error parsing workflow {workflow_path}: {str(e)}")
            return None
    
    def capture_screenshot(self, region=None):
        """Capture a screenshot of the specified region or entire screen"""
        try:
            # If no region is specified, capture the entire screen
            if region is None:
                screenshot = ImageGrab.grab()
            else:
                # region should be a tuple (left, top, right, bottom)
                screenshot = ImageGrab.grab(bbox=region)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            screenshot.save(filename)
            logging.info(f"Screenshot saved to {filename}")
            return filename
        except Exception as e:
            logging.error(f"Error capturing screenshot: {str(e)}")
            return None
    
    def generate_documentation(self, workflow_info):
        """Generate documentation for a workflow"""
        try:
            # Create a new document
            self.doc = Document()
            
            # Add title
            self.doc.add_heading(f'Alteryx Workflow Documentation: {workflow_info["name"]}', 0)
            
            # Add timestamp
            self.doc.add_paragraph(f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            
            # Add workflow overview section
            self.doc.add_heading('Workflow Overview', level=1)
            self.doc.add_paragraph(f'Workflow File: {workflow_info["name"]}')
            self.doc.add_paragraph(f'File Path: {workflow_info["path"]}')
            self.doc.add_paragraph(f'Total Components: {len(workflow_info["components"])}')
            
            # Add component summary table
            self.doc.add_heading('Component Summary', level=1)
            table = self.doc.add_table(rows=1, cols=3)
            table.style = 'Table Grid'
            header_cells = table.rows[0].cells
            header_cells[0].text = 'Component Type'
            header_cells[1].text = 'Count'
            header_cells[2].text = 'Description'
            
            # Count components by type
            component_counts = {}
            for component in workflow_info['components']:
                component_type = component['plugin'].split('.')[-1] if '.' in component['plugin'] else component['plugin']
                if component_type in component_counts:
                    component_counts[component_type] += 1
                else:
                    component_counts[component_type] = 1
            
            # Add component counts to table
            for component_type, count in component_counts.items():
                description = self.component_descriptions.get(component_type, f"Component of type {component_type}")
                row_cells = table.add_row().cells
                row_cells[0].text = component_type
                row_cells[1].text = str(count)
                row_cells[2].text = description
            
            # Add detailed component documentation
            self.doc.add_heading('Detailed Component Documentation', level=1)
            
            for component in workflow_info['components']:
                component_type = component['plugin'].split('.')[-1] if '.' in component['plugin'] else component['plugin']
                
                # Add component section
                self.doc.add_heading(f'{component_type}: {component["label"] or component["id"]}', level=2)
                self.doc.add_paragraph(f'Description: {component["description"]}')
                
                # Add properties table if there are properties
                if component['properties']:
                    self.doc.add_heading('Properties', level=3)
                    prop_table = self.doc.add_table(rows=1, cols=2)
                    prop_table.style = 'Table Grid'
                    header_cells = prop_table.rows[0].cells
                    header_cells[0].text = 'Property'
                    header_cells[1].text = 'Value'
                    
                    for prop_name, prop_value in component['properties'].items():
                        if prop_value is not None:
                            row_cells = prop_table.add_row().cells
                            row_cells[0].text = prop_name
                            # Truncate very long property values
                            if prop_value and len(prop_value) > 1000:
                                row_cells[1].text = prop_value[:1000] + "... (truncated)"
                            else:
                                row_cells[1].text = prop_value or ""
                
                # Document inputs
                if component['inputs']:
                    self.doc.add_heading('Inputs', level=3)
                    input_table = self.doc.add_table(rows=1, cols=3)
                    input_table.style = 'Table Grid'
                    header_cells = input_table.rows[0].cells
                    header_cells[0].text = 'Source ID'
                    header_cells[1].text = 'Source Type'
                    header_cells[2].text = 'Connection Name'
                    
                    for input_conn in component['inputs']:
                        row_cells = input_table.add_row().cells
                        row_cells[0].text = input_conn['source_id']
                        row_cells[1].text = input_conn['source_type']
                        row_cells[2].text = input_conn['name']
                
                # Document outputs
                if component['outputs']:
                    self.doc.add_heading('Outputs', level=3)
                    output_table = self.doc.add_table(rows=1, cols=3)
                    output_table.style = 'Table Grid'
                    header_cells = output_table.rows[0].cells
                    header_cells[0].text = 'Target ID'
                    header_cells[1].text = 'Target Type'
                    header_cells[2].text = 'Connection Name'
                    
                    for output_conn in component['outputs']:
                        row_cells = output_table.add_row().cells
                        row_cells[0].text = output_conn['target_id']
                        row_cells[1].text = output_conn['target_type']
                        row_cells[2].text = output_conn['name']
                
                # Add screenshots for key components
                if component_type in ['Input', 'Output', 'Formula', 'Summarize', 'Filter', 'Join']:
                    self.doc.add_heading('Visual Reference', level=3)
                    self.doc.add_paragraph('Note: This is a placeholder for screenshots. In a production implementation, the script would capture actual screenshots of the relevant components.')
                    # In a production implementation, you would replace this with actual component screenshots
                
                self.doc.add_paragraph('') # Add spacing between components
            
            # Add data flow diagram section
            self.doc.add_heading('Data Flow Diagram', level=1)
            self.doc.add_paragraph('Note: This section would include a visual representation of the workflow data flow.')
            
            # Add access control section
            self.doc.add_heading('Access Control', level=1)
            self.doc.add_paragraph('The following users and groups have access to this workflow and its outputs:')
            self.doc.add_paragraph('Note: This information would be populated based on system access control settings.')
            
            logging.info(f"Successfully generated documentation for workflow: {workflow_info['name']}")
            return True
        except Exception as e:
            logging.error(f"Error generating documentation: {str(e)}")
            return False
    
    def save_documentation(self, output_filename):
        """Save the documentation as Word document and optionally as PDF"""
        try:
            # Save as Word document
            word_filename = f"{output_filename}.docx"
            self.doc.save(word_filename)
            logging.info(f"Saved Word document: {word_filename}")
            print(f"Word document saved: {word_filename}")
            
            # Try to convert to PDF if library is available
            if PDF_AVAILABLE:
                try:
                    pdf_filename = f"{output_filename}.pdf"
                    convert(word_filename, pdf_filename)
                    logging.info(f"Saved PDF document: {pdf_filename}")
                    print(f"PDF document saved: {pdf_filename}")
                except Exception as pdf_error:
                    logging.error(f"Error converting to PDF: {str(pdf_error)}")
                    print(f"Warning: Could not create PDF. Error: {pdf_error}")
            else:
                print("PDF conversion skipped (docx2pdf not installed)")
            
            return word_filename
        except Exception as e:
            logging.error(f"Error saving documentation: {str(e)}")
            print(f"Error saving documentation: {str(e)}")
            return None

def main():
    """Main function to run the workflow documentation process"""
    print("Alteryx Workflow Documentation Generator")
    print("=======================================")
    
    # Get the current working directory and check for workflows there too
    current_dir = os.getcwd()
    print(f"Current working directory: {current_dir}")
    
    # Let user specify directory or use default
    workflow_dir = input("Enter the directory path containing workflow files (or press Enter for C:\\Users\\framework): ").strip()
    if not workflow_dir:
        workflow_dir = "C:\\Users\\framework"
    
    # Initialize the documenter
    documenter = AlteryxWorkflowDocumenter(workflow_dir)
    
    # Find workflow files
    workflows = documenter.find_workflow_files()
    if not workflows:
        print("No workflow files found in the specified directory.")
        print("Make sure you have .yxmd or .bak files in the directory.")
        return
    
    print(f"Found {len(workflows)} workflow files.")
    
    for i, workflow_path in enumerate(workflows):
        print(f"\nProcessing workflow {i+1}/{len(workflows)}: {os.path.basename(workflow_path)}")
        
        # Parse the workflow
        workflow_info = documenter.parse_workflow(workflow_path)
        if workflow_info is None:
            print(f"Error parsing workflow. Check the log for details.")
            continue
        
        # Generate documentation
        if documenter.generate_documentation(workflow_info):
            # Save documentation
            output_base = os.path.splitext(os.path.basename(workflow_path))[0]
            output_filename = f"{output_base}_documentation"
            saved_file = documenter.save_documentation(output_filename)
            
            if saved_file:
                print(f"Documentation saved to {saved_file}")
                if PDF_AVAILABLE:
                    print(f"PDF version also created.")
                else:
                    print(f"Only Word version created (install docx2pdf for PDF support).")
            else:
                print("Error saving documentation. Check the log for details.")
        else:
            print("Error generating documentation. Check the log for details.")
    
    print("\nDocumentation process complete.")

if __name__ == "__main__":
    main()
