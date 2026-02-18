from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"API Key found: {api_key[:10]}..." if api_key else "No API key found!")

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model='models/gemini-2.0-flash-lite',
        contents="Say 'Hello, I am working!' in one sentence."
    )
    print(f"✓ Gemini API is working!")
    print(f"Response: {response.text}")

except Exception as e:
    print(f"✗ Error: {e}")