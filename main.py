import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
import trafilatura
import time
from urllib.parse import urlparse, parse_qs, unquote

# Load environment variables (your API key)
load_dotenv()

class URLSummarizer:
    def __init__(self):
        """Initialize the summarizer with API key and keywords"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=self.api_key)
        
        # Create cloudscraper instance (bypasses Cloudflare)
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # Load keywords from JSON file
        with open('keywords.json', 'r') as f:
            self.keywords = json.load(f)
    
    def extract_real_url(self, url):
        """
        Extract real URL from Microsoft SafeLinks wrapper
        """
        if 'safelinks.protection.outlook.com' in url or 'safe.menlosecurity.com' in url:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if 'url' in params:
                    real_url = unquote(params['url'][0])
                    print(f"  → Extracted real URL from SafeLinks")
                    return real_url
            except Exception as e:
                print(f"  → Could not extract from SafeLinks: {e}")
        return url
    
    def fetch_url(self, url):
        """
        Fetch content from a URL using cloudscraper to bypass Cloudflare
        Returns: HTML content as string, or None if error
        """
        try:
            response = self.scraper.get(url, timeout=20, allow_redirects=True)
            response.raise_for_status()
            print(f"  → Fetched successfully (Status: {response.status_code}, {len(response.text)} chars)")
            return response.text
        
        except Exception as e:
            print(f"  ✗ Error fetching: {e}")
            return None
    
    def extract_article_text(self, html, url):
        """
        Extract clean article text from HTML
        Returns: Clean text content
        """
        try:
            # Method 1: trafilatura (best for news articles)
            text = trafilatura.extract(html)
            if text and len(text) > 100:
                print(f"  → Extracted {len(text)} characters using trafilatura")
                return text
            
            # Method 2: Fallback to BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            
            if text and len(text) > 100:
                print(f"  → Extracted {len(text)} characters using BeautifulSoup")
                return text
            
            return ""
        
        except Exception as e:
            print(f"  ✗ Error extracting text: {e}")
            return ""
    
    def detect_keywords(self, text):
        """
        Search text for keywords and organize by category
        Returns: Dictionary with categories and found keywords
        """
        found_keywords = {}
        text_lower = text.lower()
        
        for category, keyword_list in self.keywords.items():
            found_in_category = []
            
            for keyword in keyword_list:
                if keyword.lower() in text_lower:
                    found_in_category.append(keyword)
            
            found_keywords[category] = '; '.join(found_in_category) if found_in_category else ''
        
        return found_keywords
    
    def summarize_text(self, text, url):
        """
        Use OpenAI API to summarize the article
        Returns: Summary string
        """
        try:
            # Limit text to avoid token limits
            text = text[:8000]
            
            prompt = f"""Please provide a concise summary of this article about hydrogen trains and rail technology. 
            Focus on:
            - Key developments or announcements
            - Technical specifications mentioned
            - Timeline/dates
            - Companies or organizations involved
            - Operational details
            
            Keep the summary to 3-5 sentences.
            
            Article text:
            {text}"""
            
            print(f"  → Calling OpenAI API...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes articles about hydrogen trains and railway technology."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            print(f"  → Generated summary ({len(summary)} characters)")
            return summary
        
        except Exception as e:
            print(f"  ✗ Error summarizing: {type(e).__name__}: {e}")
            return f"ERROR: {type(e).__name__} - {str(e)[:100]}"
    
    def process_url(self, url):
        """
        Main processing function: fetch, extract, detect, summarize
        Returns: Dictionary with all results
        """
        print(f"\n{'='*60}")
        print(f"Processing: {url[:80]}...")
        
        # Step 1: Extract real URL if SafeLinks
        real_url = self.extract_real_url(url)
        if real_url != url:
            print(f"Real URL: {real_url[:80]}...")
        
        # Step 2: Fetch the URL
        html = self.fetch_url(real_url)
        if not html:
            return {
                'URL': real_url,
                'Status': 'Failed to fetch',
                'Summary': '',
                **{cat: '' for cat in self.keywords.keys()}
            }
        
        # Step 3: Extract article text
        text = self.extract_article_text(html, real_url)
        if not text or len(text) < 100:
            return {
                'URL': real_url,
                'Status': 'Failed to extract text',
                'Summary': '',
                **{cat: '' for cat in self.keywords.keys()}
            }
        
        # Step 4: Detect keywords
        keywords_found = self.detect_keywords(text)
        keyword_count = sum(1 for v in keywords_found.values() if v)
        print(f"  → Found keywords in {keyword_count}/{len(self.keywords)} categories")
        
        # Step 5: Generate summary
        summary = self.summarize_text(text, real_url)
        
        # Step 6: Combine results
        result = {
            'URL': real_url,
            'Status': 'Success',
            'Summary': summary,
            **keywords_found
        }
        
        print(f"  ✓ Completed successfully")
        return result
    
    def process_url_list(self, urls):
        """
        Process multiple URLs and save to Excel
        """
        results = []
        
        print(f"\n{'='*60}")
        print(f"Starting batch processing of {len(urls)} URLs")
        print(f"{'='*60}\n")
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}]")
            result = self.process_url(url.strip())
            results.append(result)
            
            if i < len(urls):
                print(f"\n  Waiting 2 seconds...")
                time.sleep(2)
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Reorder columns
        cols = ['URL', 'Status', 'Summary'] + list(self.keywords.keys())
        df = df[cols]
        
        # Save to Excel
        output_file = 'article_summaries.xlsx'
        df.to_excel(output_file, index=False, engine='openpyxl')
        
        # Print stats
        successful = len([r for r in results if r['Status'] == 'Success'])
        failed_fetch = len([r for r in results if r['Status'] == 'Failed to fetch'])
        failed_extract = len([r for r in results if r['Status'] == 'Failed to extract text'])
        
        print(f"\n{'='*60}")
        print(f"COMPLETE!")
        print(f"{'='*60}")
        print(f"✓ Saved to: {output_file}")
        print(f"✓ Successful: {successful}/{len(urls)}")
        print(f"✗ Failed to fetch: {failed_fetch}")
        print(f"✗ Failed to extract: {failed_extract}")
        print(f"{'='*60}\n")
        
        return df


def main():
    print("\n" + "="*60)
    print(" "*20 + "URL SUMMARIZER")
    print("="*60 + "\n")
    
    # Create summarizer instance
    try:
        summarizer = URLSummarizer()
        print("✓ Initialized successfully")
        print("✓ OpenAI client ready")
        print("✓ Keywords loaded")
    except Exception as e:
        print(f"ERROR initializing: {e}")
        print("\nCheck:")
        print("1. .env file has OPENAI_API_KEY")
        print("2. keywords.json exists")
        return
    
    # Read URLs
    try:
        with open('urls.txt', 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    except FileNotFoundError:
        print("ERROR: urls.txt not found!")
        return
    
    if not urls:
        print("ERROR: No URLs found in urls.txt")
        return
    
    print(f"✓ Found {len(urls)} URL(s) to process\n")
    
    # Process all URLs
    try:
        summarizer.process_url_list(urls)
    except KeyboardInterrupt:
        print("\nStopped by user!")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("Done! Check article_summaries.xlsx for your results!\n")


if __name__ == "__main__":
    main()