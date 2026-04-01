import re
from urllib.parse import urlparse, parse_qs, unquote

# Read the URLs
with open('urls.txt', 'r') as f:
    urls = [line.strip() for line in f if line.strip()]

print(f"Processing {len(urls)} URLs...\n")

processed_urls = []
duplicates = set()
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
            print(f"Line {i}: Warning - Could not extract from SafeLinks")
            invalid.append((i, url[:60]))
            continue
    else:
        real_url = url
    
    # Validate URL format
    if not real_url.startswith(('http://', 'https://')):
        print(f"Line {i}: Warning - Invalid URL format")
        invalid.append((i, real_url[:60]))
        continue
    
    # Check for duplicates
    if real_url in duplicates:
        print(f"Line {i}: Skipping duplicate")
        continue
    
    duplicates.add(real_url)
    processed_urls.append(real_url)
    print(f"Line {i}: OK")

print(f"\n{'='*70}")
print(f"Summary:")
print(f"  Valid URLs: {len(processed_urls)}")
print(f"  Duplicates removed: {len(urls) - len(processed_urls) - len(invalid)}")
print(f"  Invalid URLs: {len(invalid)}")

if invalid:
    print(f"\nInvalid URLs to fix:")
    for idx, url in invalid:
        print(f"  Line {idx}: {url}...")

# Write cleaned URLs back
with open('urls.txt', 'w') as f:
    for url in processed_urls:
        f.write(url + '\n')

print(f"\nURLs saved back to urls.txt ({len(processed_urls)} clean URLs)")
