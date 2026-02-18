import cloudscraper
from urllib.parse import urlparse, parse_qs, unquote

def extract_real_url(url):
    """Extract real URL from SafeLinks"""
    if 'safelinks.protection.outlook.com' in url or 'safe.menlosecurity.com' in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'url' in params:
                real_url = unquote(params['url'][0])
                return real_url
        except Exception as e:
            print(f"Error extracting: {e}")
    return url

# Read your first URL
with open('urls.txt', 'r', encoding='utf-8') as f:
    url = f.readline().strip()

print(f"Original URL: {url}\n")

# Extract real URL
real_url = extract_real_url(url)
print(f"Real URL: {real_url}\n")

# Try to fetch with cloudscraper
print("Attempting to fetch with cloudscraper...")
scraper = cloudscraper.create_scraper()

try:
    response = scraper.get(real_url, timeout=15, allow_redirects=True)
    print(f"Status Code: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"Content Length: {len(response.text)} characters")
    print(f"\nFirst 500 characters:")
    print(response.text[:500])
except Exception as e:
    print(f"ERROR: {e}")
    print(f"\nError type: {type(e).__name__}")