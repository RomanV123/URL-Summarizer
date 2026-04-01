import re
from urllib.parse import urlparse, parse_qs, unquote
from collections import Counter

# Read the URLs
with open('urls.txt', 'r') as f:
    urls = [line.strip() for line in f if line.strip()]

print(f"Processing {len(urls)} URLs...\n")

# Extract real URLs and track which line they came from
real_urls = {}
invalid = []

for i, url in enumerate(urls, 1):
    # Skip empty lines
    if not url:
        continue
    
    # Check if it's a SafeLinks URL
    if 'safelinks.protection.outlook.com' in url or 'safe.menlosecurity.com' in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'url' in params:
                real_url = unquote(params['url'][0])
            else:
                real_url = url
        except Exception as e:
            print(f"Line {i}: ERROR - Could not extract from SafeLinks")
            invalid.append((i, url[:60]))
            continue
    else:
        real_url = url
    
    # Validate URL format
    if not real_url.startswith(('http://', 'https://')):
        print(f"Line {i}: ERROR - Invalid URL format")
        invalid.append((i, real_url[:60]))
        continue
    
    # Store URL with line number
    if real_url not in real_urls:
        real_urls[real_url] = []
    real_urls[real_url].append(i)

# Find duplicates
duplicates = {url: lines for url, lines in real_urls.items() if len(lines) > 1}

print(f"\n{'='*70}")
print(f"SUMMARY:")
print(f"  Total lines in file: {len(urls)}")
print(f"  Unique URLs: {len(real_urls)}")
print(f"  Duplicate occurrences: {len(duplicates)}")
print(f"  Invalid URLs: {len(invalid)}")

if duplicates:
    print(f"\nDUPLICATE URLs (appear more than once):")
    for url, lines in duplicates.items():
        print(f"  Lines {lines}: {url[:70]}...")

if invalid:
    print(f"\nINVALID URLs:")
    for idx, url in invalid:
        print(f"  Line {idx}: {url}...")

# Create cleaned file with one copy of each unique URL
unique_urls = list(real_urls.keys())
with open('urls_cleaned.txt', 'w') as f:
    for url in unique_urls:
        f.write(url + '\n')

print(f"\n✓ Cleaned file saved as 'urls_cleaned.txt' with {len(unique_urls)} unique URLs")
print(f"  (You currently have {len(urls)} total entries)")
