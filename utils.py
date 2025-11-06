# utils.py
from dotenv import load_dotenv
import os
import json
import hashlib
import httpx
from openai import OpenAI
from colorama import init, Fore, Style
import subprocess

init(autoreset=True)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")
CACHE_FILE = os.path.join(os.path.dirname(__file__), "description_cache.json")

# Initialize OpenAI client
if not OPENAI_API_KEY:
    print(Fore.YELLOW + "OPENAI_API_KEY not set. Fallback disabled. Get it from https://platform.openai.com." + Style.RESET_ALL)
    openai_client = None
else:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        print(Fore.RED + f"Failed to initialize OpenAI client: {e}" + Style.RESET_ALL)
        openai_client = None

# Grok client wrapper
class GrokClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://api.x.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, messages, model="grok-3-beta"):
        payload = {
            "model": model,
            "messages": messages
        }
        try:
            response = httpx.post(self.endpoint, headers=self.headers, json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(Fore.RED + f"Grok API error: {e.response.status_code} - {e.response.text}" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"Grok request failed: {e}" + Style.RESET_ALL)
        return None

# Initialize Grok client
if not GROK_API_KEY:
    print(Fore.YELLOW + "GROK_API_KEY not set. Get it from https://console.grok.com." + Style.RESET_ALL)
    grok_client = None
else:
    grok_client = GrokClient(GROK_API_KEY)

BASE_DIR = os.path.dirname(__file__)
INDEX_FILE = os.path.join(BASE_DIR, "vector_index.json")
META_FILE = os.path.join(BASE_DIR, "vector_metadata.json")

def load_cache():
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(Fore.RED + f"Failed to save cache: {e}" + Style.RESET_ALL)

def get_file_hash(path):
    try:
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(Fore.RED + f"Failed to hash file {path}: {e}" + Style.RESET_ALL)
        return None

def is_poppler_available():
    try:
        subprocess.run(["pdfinfo", "-v"], capture_output=True, check=True)
        return True
    except Exception:
        return False

def is_valid_specs(specs):
    """Check if specs contain meaningful data."""
    return bool(specs and any(key in specs for key in ["Scale", "Dimensions", "Revision", "Title", "Drawing Number"]))

def chat_with_ai(prompt, model="grok-3-fast-beta", temperature=0.4, max_tokens=300, silent=False):
    """Try Grok first, then OpenAI, with better error handling."""
    messages = [{"role": "user", "content": prompt}]
    
    # Try Grok first
    if grok_client:
        try:
            if not silent:
                print(Fore.BLUE + "[→] Trying Grok..." + Style.RESET_ALL)
            resp = grok_client.chat(messages, model=model)
            if resp and "choices" in resp and len(resp["choices"]) > 0:
                result = resp["choices"][0]["message"]["content"].strip()
                if not silent:
                    print(Fore.GREEN + "[✓] Grok responded successfully." + Style.RESET_ALL)
                return result
            else:
                if not silent:
                    print(Fore.YELLOW + f"[!] Grok returned unexpected format: {resp}" + Style.RESET_ALL)
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"[!] Grok failed with error: {e}" + Style.RESET_ALL)
    else:
        if not silent:
            print(Fore.YELLOW + "[!] Grok client not initialized." + Style.RESET_ALL)
    
    # Fallback to OpenAI
    if openai_client:
        try:
            if not silent:
                print(Fore.BLUE + "[→] Falling back to OpenAI..." + Style.RESET_ALL)
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            result = resp.choices[0].message.content.strip()
            if not silent:
                print(Fore.GREEN + "[✓] OpenAI responded successfully." + Style.RESET_ALL)
            return result
        except Exception as e:
            if not silent:
                print(Fore.RED + f"[!] OpenAI fallback also failed: {e}" + Style.RESET_ALL)
    else:
        if not silent:
            print(Fore.YELLOW + "[!] OpenAI client not initialized." + Style.RESET_ALL)
    
    if not silent:
        print(Fore.RED + "[✗] Both Grok and OpenAI failed to respond." + Style.RESET_ALL)
    return None