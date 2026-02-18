from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'Hello I am working!' in one sentence."}],
        max_tokens=50
    )
    print(f"✓ OpenAI is working!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"✗ Error: {e}")