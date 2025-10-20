import requests
from requests.exceptions import RequestException

# IMPORTANT: JIRA instances almost always require authentication (API token or basic auth)
# and a proper User-Agent header. Without credentials, you will likely receive a 
# 401 (Unauthorized) or 302 (Redirect to Login) status code.

# Replace this with your actual JIRA URL
JIRA_STORY_URL = "https://track.md.com/browser/SDMOJ-11004"

# Define a simple User-Agent header to mimic a standard browser, which helps avoid
# automatic bot blocking from some servers.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def test_connection(url):
    """
    Attempts to connect to the given URL and prints the result and status code.
    """
    print(f"Attempting to connect to: {url}")
    
    try:
        # Use a timeout (10 seconds) to prevent the script from hanging indefinitely
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        # Raise an exception for bad status codes (4xx or 5xx). This makes error handling cleaner.
        response.raise_for_status() 
        
        # If the request was successful (status code 200-299)
        print("\n--- Connection Status: SUCCESS ---")
        print(f"Status Code: {response.status_code}")
        print("The server responded with content. You can likely proceed to scraping.")
        
    except requests.exceptions.ConnectionError:
        print("\n--- Connection Status: FAILED ---")
        print("Error: Could not connect to the server (DNS error, refused connection, etc.).")
    
    except requests.exceptions.Timeout:
        print("\n--- Connection Status: FAILED ---")
        print("Error: Request timed out. The server took too long to respond.")
        
    except requests.exceptions.HTTPError as e:
        # Handle 4xx client errors (like 401, 403, 404) or 5xx server errors
        print("\n--- Connection Status: FAILED (Server responded with error code) ---")
        print(f"Status Code: {e.response.status_code}")
        if e.response.status_code in [401, 403]:
             print("Reason: Unauthorized or Forbidden. This is common for JIRA. The connection works, but you need to include authentication (e.g., API token or basic auth) to access the page content.")
        else:
             print(f"Error: Received a generic bad status code ({e.response.status_code}).")

    except requests.exceptions.RequestException as e:
        # Catch all other requests-related exceptions
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    test_connection(JIRA_STORY_URL)
