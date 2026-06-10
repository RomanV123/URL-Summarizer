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
        # Poppy is OpenAI-compatible (Open WebUI backend), so we use the OpenAI
        # SDK with a custom base_url pointing at the Poppy instance.
        # Required .env values:
        #   POPPY_API_KEY   — your Poppy API key
        #   POPPY_BASE_URL  — https://customeruat.sda.state.ca.gov/api
        #                     (no trailing /v1 — the SDK appends /chat/completions)
        #   POPPY_MODEL     — exact model name from Poppy's model picker,
        #                     e.g. "Azure gpt-4.1" or "Anthropic Claude Sonnet 4.6"
        # If POPPY_BASE_URL is not set, falls back to the standard OpenAI API
        # using OPENAI_API_KEY.
        poppy_base_url = os.getenv('POPPY_BASE_URL')
        if poppy_base_url:
            self.api_key = os.getenv('POPPY_API_KEY')
            self.client = OpenAI(api_key=self.api_key, base_url=poppy_base_url)
            self.model_name = os.getenv('POPPY_MODEL', 'gpt-4o')
            self.backend_name = f"Poppy ({poppy_base_url})"
        else:
            self.api_key = os.getenv('OPENAI_API_KEY')
            self.client = OpenAI(api_key=self.api_key)
            self.model_name = 'gpt-4o'
            self.backend_name = "OpenAI (default)"
        
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
            # Method 1: trafilatura — pass URL so it can use canonical/metadata heuristics
            text = trafilatura.extract(
                html,
                url=url,
                include_tables=True,
                favor_recall=True,
                include_comments=False,
            )
            if text and len(text) > 100:
                print(f"  → Extracted {len(text)} characters using trafilatura")
                return text

            # Method 2: BeautifulSoup fallback
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                tag.decompose()
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
    
    def analyze_with_ai(self, text, url, keywords_found):
        """
        Use OpenAI to extract structured data from article
        Returns: Dictionary with all extracted information
        """
        try:
            text = text[:20000]  # Higher limit reduces mid-article truncation

            # Build keyword context string from detected keywords
            keyword_context_parts = []
            for category, matches in keywords_found.items():
                if matches:
                    keyword_context_parts.append(f"  - {category}: {matches}")
            keyword_context = "\n".join(keyword_context_parts) if keyword_context_parts else "  - (none detected)"

            prompt = f"""Analyze this article about zero-emission transportation and extract the following information in JSON format:

{{
  "summary": "Provide a COMPREHENSIVE 6-10 sentence summary that includes: (1) the main development or announcement with specific details, (2) ALL technical specifications mentioned (capacities, ranges, power outputs, dimensions, etc.), (3) exact timeline information and dates, (4) all companies/organizations involved and their specific roles, (5) operational details (routes, frequency, passenger capacity, etc.), (6) technical processes or methodologies described, (7) funding amounts and sources, (8) regulatory or policy context. Be specific with numbers, units, and technical terms. Do not abbreviate or simplify technical information.",
  "primary_category": "One of: Rail, Trucks, Ports/Marine, Aviation, Infrastructure, Buses/Transit, or Other",
  "subcategory": "A more specific subcategory within the chosen primary_category. Pick from the list that matches primary_category (see SUBCATEGORY OPTIONS below). Use empty string if primary_category is Other.",
  "project_stage": "One of: Announced, In Development, Pilot/Trial, Operational, Completed, Cancelled",
  "article_date": "Publication date in YYYY-MM-DD format if found, otherwise null",
  "project_dates": [
    {{
      "date": "YYYY-MM-DD or YYYY-MM or YYYY or Q# YYYY format",
      "milestone": "Brief description of what happens at this date (e.g., 'prototype testing begins', 'commercial launch', 'funding approved', 'regulatory approval expected', 'construction starts', 'pilot program ends')",
      "type": "One of: announced, planned, target, expected, completed, ongoing"
    }}
  ],
  "companies": ["List of ALL companies/organizations mentioned"]
}}

SUBCATEGORY OPTIONS (pick one that matches primary_category):
  - Rail: Passenger Rail, Freight Rail, Commuter Rail, Light Rail, Locomotive, Other
  - Trucks: Drayage, Long-Haul, Class 8, Medium-Duty, Last-Mile Delivery, Other
  - Ports/Marine: Cargo Vessel, Ferry, Tug/Workboat, Port Operations, Bunkering, Other
  - Aviation: Commercial, Regional, eVTOL, Cargo, General Aviation, Other
  - Infrastructure: Refueling Station, Production Facility, Storage, Distribution Pipeline, Other
  - Buses/Transit: Transit Bus, School Bus, Shuttle, Bus Rapid Transit, Other
  - Other: leave empty

CRITICAL INSTRUCTIONS:
1. The summary must be detailed and comprehensive. Include all technical specifications, exact numbers with units, specific methodologies (like "HYFOR process", "PEM electrolyser", "DEMU train"), partnership details, and operational specifics. Do not generalize or simplify technical information.

2. CATEGORIZATION RULES — read carefully:
   - "Ports/Marine" covers ALL vessels, ships, ferries, tugboats, marine fuel cell systems, port operations, bunkering, and shipping. If the article is about a hydrogen-powered boat, ferry, or marine fuel cell, choose Ports/Marine — NOT Other.
   - "Infrastructure" covers standalone hydrogen refueling stations, electrolyzers, hydrogen production sites, storage facilities, and pipelines that aren't tied to a specific transportation mode.
   - "Buses/Transit" covers buses, transit shuttles, BRT, and public transportation projects.
   - Only choose "Other" if the article genuinely doesn't fit any named sector. If it spans multiple sectors, pick the one that is the DOMINANT focus of the article.
   - Always pick a subcategory that matches the primary_category. If unsure within a category, use "Other" as the subcategory.

3. The following relevant keywords were detected in this article — pay close attention to these topics when writing the summary and extracting information:
{keyword_context}

4. For project_dates, extract EVERY date/timeline mentioned with context:
   - Include years (2025, 2027), quarters (Q1 2025), months (September 2025), and specific dates (July 29, 2025)
   - For each date, specify what milestone/event it refers to
   - Mark the type: "completed" for past events, "ongoing" for current, "planned/target/expected" for future
   - Include funding dates, testing dates, operational dates, regulatory dates, construction dates, etc.
   - If article says "by 2026" or "by end of 2026", mark as "target" with date 2026-12-31
   - If article says "in 2027", mark as "expected" with date 2027
   - Extract both the announcement date AND the project timeline dates

5. For project_stage, choose the CURRENT state of the project as described in the article:
   - "Announced" = recently announced but work has not yet started
   - "In Development" = design, engineering, manufacturing, or construction underway
   - "Pilot/Trial" = limited testing or demonstration phase
   - "Operational" = actively running in commercial or revenue service
   - "Completed" = the project's defined scope is finished; no further milestones planned
   - "Cancelled" = the project has been halted, abandoned, or cancelled

Article text:
{text}

Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."""

            print(f"  → Calling {self.backend_name} ({self.model_name}) for detailed structured analysis...")

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing transportation and hydrogen technology articles. You extract comprehensive, detailed information with all technical specifications, numbers, and specific terminology intact. You never abbreviate or generalize technical details. You are especially thorough at extracting ALL dates and timelines with their context."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=3000,
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
            "subcategory": "",
            "project_stage": "",
            "article_date": None,
            "project_dates": [],
            "companies": []
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
    
    def check_timeline_flag(self, project_stage, project_dates):
        """
        Decide the Timeline_Flag for the row based on project stage and dates.

        Priority order:
          - "❌ CANCELLED" if the LLM marked the project as Cancelled.
          - "✓ COMPLETED" if the LLM marked the project as Completed.
          - "⚠️ PAST PROJECT" if any completed/ongoing date is more than one year
            before the current year and there are no future dates.
          - "" otherwise.
        """
        # Direct stage-based flags
        if project_stage == "Cancelled":
            return "❌ CANCELLED"
        if project_stage == "Completed":
            return "✓ COMPLETED"

        current_year = datetime.now().year
        has_future_date = False
        has_stale_past_date = False

        for date_info in project_dates:
            try:
                date_str = str(date_info.get('date', ''))
                date_type = date_info.get('type', '')

                year_digits = ''.join(filter(str.isdigit, date_str))[:4]
                if not year_digits:
                    continue
                year = int(year_digits)

                if year >= current_year:
                    has_future_date = True

                if date_type in ['completed', 'ongoing'] and year < current_year - 1:
                    has_stale_past_date = True
            except Exception:
                continue

        if has_stale_past_date and not has_future_date:
            return "⚠️ PAST PROJECT"

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
        
        # AI-powered structured analysis (pass keywords as context)
        ai_result = self.analyze_with_ai(text, real_url, keywords_found)

        # Format project dates
        formatted_dates = self.format_project_dates(ai_result.get('project_dates', []))

        # Check timeline flag using both project_stage and project_dates
        timeline_flag = self.check_timeline_flag(
            ai_result.get('project_stage', ''),
            ai_result.get('project_dates', [])
        )

        # Combine results
        result = {
            'URL': real_url,
            'Status': 'Success',
            'Timeline_Flag': timeline_flag,
            'Primary_Category': ai_result.get('primary_category', 'Unknown'),
            'Subcategory': ai_result.get('subcategory', ''),
            'Project_Stage': ai_result.get('project_stage', ''),
            'Article_Date': ai_result.get('article_date', 'Unknown'),
            'Summary': ai_result.get('summary', 'No summary available'),
            'Companies_Mentioned': '; '.join(ai_result.get('companies', [])),
            'Project_Dates': formatted_dates,
        }
        
        print(f"  ✓ Completed successfully")
        return result
    
    def _create_failed_result(self, url, status):
        """Create result dictionary for failed processing"""
        return {
            'URL': url,
            'Status': status,
            'Timeline_Flag': '',
            'Primary_Category': '',
            'Subcategory': '',
            'Project_Stage': '',
            'Article_Date': '',
            'Summary': '',
            'Companies_Mentioned': '',
            'Project_Dates': '',
        }
    
    COL_ORDER = [
        'URL', 'Status', 'Timeline_Flag', 'Primary_Category', 'Subcategory',
        'Project_Stage', 'Article_Date', 'Summary', 'Companies_Mentioned',
        'Project_Dates',
    ]

    def save_to_excel(self, results):
        """Append results to article_summaries.xlsx, skipping duplicate URLs."""
        df = pd.DataFrame(results)
        output_file = 'article_summaries.xlsx'

        if os.path.exists(output_file):
            existing_df = pd.read_excel(output_file)
            existing_df = existing_df[[c for c in self.COL_ORDER if c in existing_df.columns]]
            existing_urls = set(existing_df['URL'].astype(str))
            new_rows = df[~df['URL'].isin(existing_urls)]
            if len(new_rows) > 0:
                df = pd.concat([existing_df, new_rows], ignore_index=True)
            else:
                df = existing_df

        df = df[[c for c in self.COL_ORDER if c in df.columns]]
        df.to_excel(output_file, index=False, engine='openpyxl')
        return output_file

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

        output_file = self.save_to_excel(results)

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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N URLs (useful for testing)')
    args = parser.parse_args()

    print("\n" + "="*60)
    print(" "*15 + "ADVANCED URL SUMMARIZER")
    print("="*60 + "\n")

    try:
        summarizer = URLSummarizer()
        print("✓ Initialized successfully")
        print(f"✓ API client ready — using {summarizer.backend_name}")
        print(f"✓ Model: {summarizer.model_name}")
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

    if args.limit:
        urls = urls[:args.limit]
        print(f"✓ Test mode: processing first {len(urls)} URL(s)\n")
    else:
        print(f"✓ Found {len(urls)} URL(s) to process\n")

    # Process URLs
    try:
        summarizer.process_url_list(urls)
    except KeyboardInterrupt:
        print("\nStopped by user!")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    print("Done! Check your Excel file for results!\n")


if __name__ == "__main__":
    main()
