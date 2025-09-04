import requests
import json
import pandas as pd
from typing import Dict, List, Any
import time
from urllib.parse import urljoin, urlparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JiraProjectScraper:
    def __init__(self, base_url: str, session_cookies: Dict[str, str] = None):
        """
        Initialize the scraper with base URL and optional session cookies
        
        Args:
            base_url: Base URL of the Confluence/Jira system
            session_cookies: Dictionary of cookies for authentication
        """
        self.base_url = base_url
        self.session = requests.Session()
        if session_cookies:
            self.session.cookies.update(session_cookies)
        
        # Issue types found in your system
        self.issue_types = [
            'Epic', 'Story', 'Risk', 'Task', 'Mitigation Plan', 'Bug', 
            'Request', 'Incident', 'Project Item', 'Risk (RAID)', 
            'Action', 'Issue', 'Decision'
        ]
    
    def get_project_issue_types(self, project_key: str) -> List[str]:
        """
        Get available issue types for a project
        
        Args:
            project_key: The project key (e.g., 'AMCBDA')
            
        Returns:
            List of available issue types for the project
        """
        url = f"{self.base_url}/confiforms/jira-issue-mapping.action"
        params = {
            'applinkName': 'JIRA',
            'projectKey': project_key
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            # Parse the response to extract available issue types
            # This would need to be adapted based on the actual response format
            available_types = []
            if 'Epic' in response.text:
                available_types.extend(self.issue_types)
            
            return available_types
        except requests.RequestException as e:
            logger.error(f"Error fetching issue types for {project_key}: {e}")
            return []
    
    def get_field_mapping(self, project_key: str, issue_type: str) -> Dict[str, Any]:
        """
        Get field mapping for a specific project and issue type
        
        Args:
            project_key: The project key (e.g., 'AMCBDA')
            issue_type: The issue type (e.g., 'Epic')
            
        Returns:
            Dictionary containing the field mapping
        """
        url = f"{self.base_url}/confiforms/jira-issue-mapping.action"
        params = {
            'applinkName': 'JIRA',
            'projectKey': project_key,
            'issueType': issue_type
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            # Extract JSON data from response
            # Based on your image, it looks like there's a JSON structure in the response
            response_text = response.text
            
            # Look for JSON pattern in the response
            start_marker = '{"fields":'
            if start_marker in response_text:
                start_idx = response_text.find(start_marker)
                # Find the end of JSON (this is a simple approach, might need refinement)
                json_str = response_text[start_idx:]
                # Try to find the end bracket
                bracket_count = 0
                end_idx = 0
                for i, char in enumerate(json_str):
                    if char == '{':
                        bracket_count += 1
                    elif char == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_idx = i + 1
                            break
                
                if end_idx > 0:
                    json_str = json_str[:end_idx]
                    try:
                        field_data = json.loads(json_str)
                        field_data['project_key'] = project_key
                        field_data['issue_type'] = issue_type
                        return field_data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error for {project_key}-{issue_type}: {e}")
            
            return {}
            
        except requests.RequestException as e:
            logger.error(f"Error fetching field mapping for {project_key}-{issue_type}: {e}")
            return {}
    
    def flatten_field_mapping(self, field_mapping: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten the field mapping structure for easier tabulation
        
        Args:
            field_mapping: The field mapping dictionary
            
        Returns:
            Flattened dictionary
        """
        flattened = {
            'project_key': field_mapping.get('project_key', ''),
            'issue_type': field_mapping.get('issue_type', ''),
        }
        
        fields = field_mapping.get('fields', {})
        
        # Extract common fields based on your image
        field_mappings = {
            'epic_name': 'customfield_10007',
            'control_delivery_partners': 'customfield_25405',
            'components': 'components',
            'impacted_regulations': 'customfield_25407',
            'description': 'description',
            'fix_versions': 'fixVersions',
            'parent_link': 'customfield_19601',
            'time_tracking': 'timetracking',
            'jira_datetime': 'customfield_11413',
            'security_level': 'security',
            'theme': 'customfield_22900',
            'pod_name': 'customfield_22800',
            'summary': 'summary',
            'classification': 'customfield_18604',
            'sub_class': 'customfield_18605',
            'priority': 'priority',
            'business_value': 'customfield_10003',
            'labels': 'labels',
            'executive_sponsor': 'customfield_17706',
            'affects_versions': 'versions',
            'assignee': 'assignee',
            'linked_issues': 'issuelinks',
            'business_segment': 'customfield_25400',
            'business_lead': 'customfield_25401',
            'business_intake_number': 'customfield_25402'
        }
        
        # Extract field values
        for readable_name, field_key in field_mappings.items():
            field_data = fields.get(field_key, {})
            if isinstance(field_data, dict):
                if 'name' in field_data:
                    flattened[readable_name] = field_data['name']
                elif 'id' in field_data:
                    flattened[readable_name] = field_data.get('id', '')
                else:
                    flattened[readable_name] = str(field_data)
            elif isinstance(field_data, list):
                flattened[readable_name] = ', '.join([
                    item.get('name', str(item)) if isinstance(item, dict) else str(item) 
                    for item in field_data
                ])
            else:
                flattened[readable_name] = str(field_data) if field_data else ''
        
        return flattened
    
    def scrape_project_data(self, project_keys: List[str]) -> pd.DataFrame:
        """
        Scrape data for multiple project keys
        
        Args:
            project_keys: List of project keys to scrape
            
        Returns:
            DataFrame with all scraped data
        """
        all_data = []
        
        for project_key in project_keys:
            logger.info(f"Processing project: {project_key}")
            
            # Get available issue types for this project
            available_types = self.get_project_issue_types(project_key)
            if not available_types:
                available_types = self.issue_types  # Fallback to all types
            
            for issue_type in available_types:
                logger.info(f"  Processing issue type: {issue_type}")
                
                # Get field mapping
                field_mapping = self.get_field_mapping(project_key, issue_type)
                
                if field_mapping and 'fields' in field_mapping:
                    # Flatten and add to results
                    flattened_data = self.flatten_field_mapping(field_mapping)
                    all_data.append(flattened_data)
                
                # Add delay to be respectful to the server
                time.sleep(1)
        
        # Convert to DataFrame
        if all_data:
            df = pd.DataFrame(all_data)
            return df
        else:
            return pd.DataFrame()
    
    def save_to_files(self, df: pd.DataFrame, output_prefix: str = "jira_data"):
        """
        Save the scraped data to various formats
        
        Args:
            df: DataFrame with scraped data
            output_prefix: Prefix for output files
        """
        if df.empty:
            logger.warning("No data to save")
            return
        
        # Save as CSV
        csv_file = f"{output_prefix}.csv"
        df.to_csv(csv_file, index=False)
        logger.info(f"Data saved to {csv_file}")
        
        # Save as Excel with separate sheets for each project
        excel_file = f"{output_prefix}.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            # Overall data
            df.to_excel(writer, sheet_name='All_Data', index=False)
            
            # Separate sheets for each project
            for project_key in df['project_key'].unique():
                project_data = df[df['project_key'] == project_key]
                sheet_name = f"Project_{project_key}"[:31]  # Excel sheet name limit
                project_data.to_excel(writer, sheet_name=sheet_name, index=False)
        
        logger.info(f"Data saved to {excel_file}")
        
        # Generate summary statistics
        self.generate_summary_report(df, f"{output_prefix}_summary.txt")
    
    def generate_summary_report(self, df: pd.DataFrame, output_file: str):
        """
        Generate a summary report of the scraped data
        
        Args:
            df: DataFrame with scraped data
            output_file: Output file for the summary
        """
        with open(output_file, 'w') as f:
            f.write("JIRA Project Data Scraping Summary\n")
            f.write("=" * 40 + "\n\n")
            
            f.write(f"Total records: {len(df)}\n")
            f.write(f"Total projects: {df['project_key'].nunique()}\n")
            f.write(f"Total issue types: {df['issue_type'].nunique()}\n\n")
            
            f.write("Projects processed:\n")
            for project in df['project_key'].unique():
                count = len(df[df['project_key'] == project])
                f.write(f"  - {project}: {count} records\n")
            
            f.write("\nIssue types found:\n")
            for issue_type in df['issue_type'].unique():
                count = len(df[df['issue_type'] == issue_type])
                f.write(f"  - {issue_type}: {count} records\n")
        
        logger.info(f"Summary report saved to {output_file}")

# Example usage
def main():
    # Configuration
    PROJECT_KEYS = ["AMCBDA"]  # Add more project keys as needed
    
    # Initialize scraper
    scraper = JiraProjectScraper()
    
    # If you need authentication, add cookies here
    # You can get these from your browser's developer tools
    # scraper.session.cookies.update({
    #     'JSESSIONID': 'your_session_id',
    #     'confluence.browse.space.cookie': 'your_space_cookie'
    # })
    
    try:
        # Scrape data
        logger.info("Starting data scraping...")
        df = scraper.scrape_project_data(PROJECT_KEYS)
        
        if not df.empty:
            # Save results
            scraper.save_to_files(df, "jira_project_data")
            
            # Display basic info
            print(f"\nScraping completed successfully!")
            print(f"Total records scraped: {len(df)}")
            print(f"Projects: {', '.join(df['project_key'].unique())}")
            print(f"Issue types: {', '.join(df['issue_type'].unique())}")
        else:
            print("No data was scraped. Please check your authentication and network connectivity.")
            
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        raise

if __name__ == "__main__":
    main()
