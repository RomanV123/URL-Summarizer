#main.py
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
import trafilatura
import time

load_dotenv()

class URLSummarizer:

    def __init__(self):
        api_key = load_dotenv()
        self.api_key = os.getenv('OPEN_API_KEY')
        self.client = OpenAI(api_key=self.api_key)
        with open('keywords.json', 'r') as f:
            self.keywords = json.load(f)

    def fetch_url(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers = headers, timeout = 10)
            response.raise_for_status()

            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
        
    def extract_article_text(self,html,url):
        try:
            text = trafilatura.extract(html)

            if text:
                return text
            
            soup = BeautifulSoup(html, 'html.parser')

            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            text = soup.get_text(seperator = ' ', strip=True)

            return text
        
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
        
    



