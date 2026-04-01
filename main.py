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
from datetime import datetime

# Load environment variables
load_dotenv()

class URLSummarizer:
    def __init__(self):
        """Initialize the summarizer with API key and keywords"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=self.api_key)
        
        # Create cloudscraper instance
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
        
        # Today's date for timeline comparison
        self.today = datetime.now().date()
    
    def extract_real_url(self, url):
        """Extract real URL from SafeLinks wrapper"""
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
        """Fetch content from URL using cloudscraper"""
        try:
            response = self.scraper.get(url, timeout=20, allow_redirects=True)
            response.raise_for_status()
            print(f"  → Fetched successfully (Status: {response.status_code}, {len(response.text)} chars)")
            return response.text
        except Exception as e:
            print(f"  ✗ Error fetching: {e}")
            return None
    
    def extract_article_text(self, html, url):
        """Extract clean article text from HTML"""
        try:
            # Method 1: trafilatura
            text = trafilatura.extract(html)
            if text and len(text) > 100:
                print(f"  → Extracted {len(text)} characters using trafilatura")
                return text
            
            # Method 2: BeautifulSoup fallback
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
        """Search text for keywords and organize by category"""
        found_keywords = {}
        text_lower = text.lower()
        
        for category, keyword_list in self.keywords.items():
            found_in_category = []
            for keyword in keyword_list:
                if keyword.lower() in text_lower:
                    found_in_category.append(keyword)
            found_keywords[category] = '; '.join(found_in_category) if found_in_category else ''
        
        return found_keywords
    
    def analyze_with_ai(self, text, url):
        """
        Use OpenAI to extract structured data from article
        Returns: Dictionary with all extracted information
        """
        try:
            text = text[:12000]  # Increased limit for better analysis
            
            prompt = f"""Analyze this article about zero-emission transportation and extract the following information in JSON format:

{{
  "summary": "Provide a COMPREHENSIVE 6-10 sentence summary that includes: (1) the main development or announcement with specific details, (2) ALL technical specifications mentioned (capacities, ranges, power outputs, dimensions, etc.), (3) exact timeline information and dates, (4) all companies/organizations involved and their specific roles, (5) operational details (routes, frequency, passenger capacity, etc.), (6) technical processes or methodologies described, (7) funding amounts and sources, (8) regulatory or policy context. Be specific with numbers, units, and technical terms. Do not abbreviate or simplify technical information.",
  "primary_category": "One of: Rail, Trucks, Ports, Aviation, or Other",
  "rail_type": "passenger, freight, both, or unknown (only if primary_category is Rail)",
  "article_date": "Publication date in YYYY-MM-DD format if found, otherwise null",
  "project_dates": [
    {{
      "date": "YYYY-MM-DD or YYYY-MM or YYYY or Q# YYYY format",
      "milestone": "Brief description of what happens at this date (e.g., 'prototype testing begins', 'commercial launch', 'funding approved', 'regulatory approval expected', 'construction starts', 'pilot program ends')",
      "type": "One of: announced, planned, target, expected, completed, ongoing"
    }}
  ],
  "companies": ["List of ALL companies/organizations mentioned"],
  "locations": ["Countries, regions, or cities mentioned"]
}}

CRITICAL INSTRUCTIONS:
1. The summary must be detailed and comprehensive. Include all technical specifications, exact numbers with units, specific methodologies (like "HYFOR process", "PEM electrolyser", "DEMU train"), partnership details, and operational specifics. Do not generalize or simplify technical information.

2. For project_dates, extract EVERY date/timeline mentioned with context:
   - Include years (2025, 2027), quarters (Q1 2025), months (September 2025), and specific dates (July 29, 2025)
   - For each date, specify what milestone/event it refers to
   - Mark the type: "completed" for past events, "ongoing" for current, "planned/target/expected" for future
   - Include funding dates, testing dates, operational dates, regulatory dates, construction dates, etc.
   - If article says "by 2026" or "by end of 2026", mark as "target" with date 2026-12-31
   - If article says "in 2027", mark as "expected" with date 2027
   - Extract both the announcement date AND the project timeline dates

Article text:
{text}

Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."""

            print(f"  → Calling OpenAI API for detailed structured analysis...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing transportation and hydrogen technology articles. You extract comprehensive, detailed information with all technical specifications, numbers, and specific terminology intact. You never abbreviate or generalize technical details. You are especially thorough at extracting ALL dates and timelines with their context."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.2
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Remove markdown code fences if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            # Parse JSON
            result = json.loads(result_text)
            
            print(f"  → Analysis complete: {result['primary_category']}")
            print(f"  → Summary length: {len(result.get('summary', ''))} characters")
            print(f"  → Found {len(result.get('project_dates', []))} project dates")
            
            return result
        
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parsing error: {e}")
            print(f"  Raw response: {result_text[:200]}...")
            return self._get_error_result("JSON parsing failed")
        
        except Exception as e:
            print(f"  ✗ Error in AI analysis: {type(e).__name__}: {e}")
            return self._get_error_result(str(e))
    
    def _get_error_result(self, error_msg):
        """Return error structure when AI analysis fails"""
        return {
            "summary": f"ERROR: {error_msg}",
            "primary_category": "Error",
            "rail_type": "unknown",
            "article_date": None,
            "project_dates": [],
            "companies": [],
            "locations": []
        }
    
    def format_project_dates(self, project_dates):
        """
        Format project dates into a readable string
        Returns: Formatted string with dates and milestones
        """
        if not project_dates:
            return ""
        
        formatted_dates = []
        for date_info in project_dates:
            date = date_info.get('date', 'Unknown')
            milestone = date_info.get('milestone', '')
            date_type = date_info.get('type', '')
            
            # Format: "2027 (target): Commercial launch"
            if milestone:
                formatted = f"{date} ({date_type}): {milestone}"
            else:
                formatted = f"{date} ({date_type})"
            
            formatted_dates.append(formatted)
        
        return ' | '.join(formatted_dates)
    
    def check_timeline_flag(self, project_dates):
        """
        Check if project is in the past (completion date before today)
        Returns: "PAST" if any project date is before 2026, else ""
        """
        for date_info in project_dates:
            try:
                date_str = date_info.get('date', '')
                date_type = date_info.get('type', '')
                
                # Only flag if it's a completion/operational date, not announcement dates
                if date_type in ['completed', 'ongoing']:
                    # Extract year from string
                    year = int(''.join(filter(str.isdigit, str(date_str)))[:4])
                    if year < 2026:
                        return "⚠️ PAST PROJECT"
            except:
                continue
        
        return ""
    
    def process_url(self, url):
        """Main processing function"""
        print(f"\n{'='*60}")
        print(f"Processing: {url[:80]}...")
        
        # Extract real URL if SafeLinks
        real_url = self.extract_real_url(url)
        if real_url != url:
            print(f"Real URL: {real_url[:80]}...")
        
        # Fetch the URL
        html = self.fetch_url(real_url)
        if not html:
            return self._create_failed_result(real_url, 'Failed to fetch')
        
        # Extract article text
        text = self.extract_article_text(html, real_url)
        if not text or len(text) < 100:
            return self._create_failed_result(real_url, 'Failed to extract text')
        
        # Detect keywords (traditional method)
        keywords_found = self.detect_keywords(text)
        keyword_count = sum(1 for v in keywords_found.values() if v)
        print(f"  → Found keywords in {keyword_count}/{len(self.keywords)} categories")
        
        # AI-powered structured analysis
        ai_result = self.analyze_with_ai(text, real_url)
        
        # Format project dates
        formatted_dates = self.format_project_dates(ai_result.get('project_dates', []))
        
        # Check timeline flag
        timeline_flag = self.check_timeline_flag(ai_result.get('project_dates', []))
        
        # Combine results
        result = {
            'URL': real_url,
            'Status': 'Success',
            'Timeline_Flag': timeline_flag,
            'Primary_Category': ai_result.get('primary_category', 'Unknown'),
            'Rail_Type': ai_result.get('rail_type', 'N/A'),
            'Article_Date': ai_result.get('article_date', 'Unknown'),
            'Summary': ai_result.get('summary', 'No summary available'),
            'Companies_Mentioned': '; '.join(ai_result.get('companies', [])),
            'Project_Dates': formatted_dates,
            'Locations': '; '.join(ai_result.get('locations', [])),
            'Funding': ai_result.get('funding', ''),
            **keywords_found  # Add traditional keyword detection results
        }
        
        print(f"  ✓ Completed successfully")
        return result
    
    def _create_failed_result(self, url, status):
        """Create result dictionary for failed processing"""
        base_result = {
            'URL': url,
            'Status': status,
            'Timeline_Flag': '',
            'Primary_Category': '',
            'Rail_Type': '',
            'Article_Date': '',
            'Summary': '',
            'Companies_Mentioned': '',
            'Project_Dates': '',
            'Locations': '',
            'Funding': ''
        }
        # Add empty strings for all keyword categories
        for category in self.keywords.keys():
            base_result[category] = ''
        return base_result
    
    def process_url_list(self, urls):
        """Process multiple URLs and save to Excel"""
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
        
        # Reorder columns for better Excel layout
        priority_cols = [
            'URL', 'Status', 'Timeline_Flag', 'Primary_Category', 'Rail_Type',
            'Article_Date', 'Summary', 'Companies_Mentioned', 'Project_Dates', 
            'Locations', 'Funding'
        ]
        
        # Add keyword category columns
        keyword_cols = list(self.keywords.keys())
        all_cols = priority_cols + keyword_cols
        
        # Reorder (only include columns that exist)
        existing_cols = [col for col in all_cols if col in df.columns]
        df = df[existing_cols]
        
        # Save to Excel (single persistent file)
        output_file = 'article_summaries.xlsx'
        
        # If file exists, read existing data and append new results (avoiding duplicates)
        if os.path.exists(output_file):
            existing_df = pd.read_excel(output_file)
            existing_urls = set(existing_df['URL'].astype(str))
            new_urls = set(df['URL'].astype(str))
            
            # Only append rows that aren't already in the file
            new_rows = df[~df['URL'].isin(existing_urls)]
            if len(new_rows) > 0:
                df = pd.concat([existing_df, new_rows], ignore_index=True)
            else:
                df = existing_df
        
        df.to_excel(output_file, index=False, engine='openpyxl')
        
        # Print stats
        successful = len([r for r in results if r['Status'] == 'Success'])
        failed_fetch = len([r for r in results if r['Status'] == 'Failed to fetch'])
        failed_extract = len([r for r in results if r['Status'] == 'Failed to extract text'])
        past_projects = len([r for r in results if r.get('Timeline_Flag', '')])
        
        print(f"\n{'='*60}")
        print(f"COMPLETE!")
        print(f"{'='*60}")
        print(f"✓ Saved to: {output_file}")
        print(f"✓ Successful: {successful}/{len(urls)}")
        print(f"✗ Failed to fetch: {failed_fetch}")
        print(f"✗ Failed to extract: {failed_extract}")
        print(f"⚠️  Past projects flagged: {past_projects}")
        print(f"{'='*60}\n")
        
        return df


def main():
    print("\n" + "="*60)
    print(" "*15 + "ADVANCED URL SUMMARIZER")
    print("="*60 + "\n")
    
    try:
        summarizer = URLSummarizer()
        print("✓ Initialized successfully")
        print("✓ OpenAI client ready")
        print(f"✓ {len(summarizer.keywords)} keyword categories loaded")
    except Exception as e:
        print(f"ERROR initializing: {e}")
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
    
    print("Done! Check your timestamped Excel file for results!\n")


if __name__ == "__main__":
    main()
