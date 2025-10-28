import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth
import json

# Configuration
JIRA_STORY_URL = "https://track.md.com/browse/SDMOJ-11004"
JIRA_USER = "your.email@company.com"
JIRA_PASSWORD = "your_password"  # Your actual JIRA password (not API token)

PROXIES = None  # Configure if needed

def scrape_jira_story(url):
    """Scrape JIRA story details from the HTML page"""
    
    print(f"Scraping: {url}")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Set headers to mimic a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        # First, try without authentication (if page is public)
        response = session.get(url, headers=headers, proxies=PROXIES, timeout=10)
        
        # If redirected to login, you'll need to authenticate
        if 'login' in response.url.lower() or response.status_code == 401:
            print("Authentication required...")
            # Use basic auth
            auth = HTTPBasicAuth(JIRA_USER, JIRA_PASSWORD)
            response = session.get(url, headers=headers, auth=auth, proxies=PROXIES, timeout=10)
        
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract data (selectors may vary by JIRA version)
        story_data = {}
        
        # Issue Key
        issue_key = soup.find('a', {'id': 'key-val'})
        story_data['key'] = issue_key.text.strip() if issue_key else None
        
        # Summary/Title
        summary = soup.find('h1', {'id': 'summary-val'})
        story_data['summary'] = summary.text.strip() if summary else None
        
        # Description
        description = soup.find('div', {'id': 'description-val'})
        story_data['description'] = description.get_text(strip=True) if description else None
        
        # Status
        status = soup.find('span', {'id': 'status-val'})
        story_data['status'] = status.text.strip() if status else None
        
        # Assignee
        assignee = soup.find('span', {'id': 'assignee-val'})
        story_data['assignee'] = assignee.get_text(strip=True) if assignee else None
        
        # Reporter
        reporter = soup.find('span', {'id': 'reporter-val'})
        story_data['reporter'] = reporter.get_text(strip=True) if reporter else None
        
        # Priority
        priority = soup.find('span', {'id': 'priority-val'})
        story_data['priority'] = priority.text.strip() if priority else None
        
        # Custom fields (adjust based on your JIRA)
        custom_fields = soup.find_all('div', {'class': 'field-group'})
        for field in custom_fields:
            label = field.find('strong')
            value = field.find('div', {'class': 'value'})
            if label and value:
                story_data[label.text.strip()] = value.get_text(strip=True)
        
        # Print extracted data
        print("\n=== Extracted Data ===")
        for key, value in story_data.items():
            print(f"{key}: {value}")
        
        # Save to JSON
        filename = f"{story_data.get('key', 'jira_story')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(story_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Saved to: {filename}")
        
        return story_data
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error: {e}")
        return None

if __name__ == "__main__":
    scrape_jira_story(JIRA_STORY_URL)
