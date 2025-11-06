#utils.py
#**************************************************************************************************
#   utils.py provides utility functions for interacting with AI models (Grok and OpenAI), 
#   caching file descriptions, and cleaning extracted specifications.
#**************************************************************************************************
from dotenv import load_dotenv
import os
import json
import hashlib
import httpx
import time
import re
from colorama import Fore, Style
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

class GrokClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://api.x.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, messages, model="grok-3-fast-beta"):
        payload = {"model": model, "messages": messages}
        try:
            response = httpx.post(self.endpoint, headers=self.headers, json=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except:
            return None

grok_client = GrokClient(GROK_API_KEY) if GROK_API_KEY else None

CACHE_FILE = os.path.join(os.path.dirname(__file__), "description_cache.json")

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
    except:
        pass

def get_file_hash(path):
    try:
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None

def is_valid_specs(specs):
    if not specs:
        return False
    for value in specs.values():
        if value:
            return True
    return False

def clean_specs(specs):
    """Remove noise and clean up extracted specs."""
    if not specs:
        return specs
    
    cleaned = {}
    noise_patterns = [
        r"^(is the sole property|any reproduction|approved)",
        r"^(rev date description)",
        r"^\s*$",
    ]
    
    for key, value in specs.items():
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                item_str = str(item).strip()
                is_noise = any(re.search(pattern, item_str, re.IGNORECASE) for pattern in noise_patterns)
                if not is_noise and len(item_str) > 1:
                    cleaned_list.append(item_str)
            if cleaned_list:
                cleaned[key] = cleaned_list
        elif isinstance(value, str):
            value_str = value.strip()
            is_noise = any(re.search(pattern, value_str, re.IGNORECASE) for pattern in noise_patterns)
            if not is_noise and len(value_str) > 1:
                cleaned[key] = value_str
    
    return cleaned

def chat_with_ai(prompt, model="grok-3-fast-beta", temperature=0.4, max_tokens=300, silent=False):
    """Try Grok first, then OpenAI."""
    messages = [{"role": "user", "content": prompt}]
    
    if grok_client:
        try:
            if not silent:
                print(Fore.BLUE + "Using Grok..." + Style.RESET_ALL)
            resp = grok_client.chat(messages, model=model)
            if resp and "choices" in resp and len(resp["choices"]) > 0:
                result = resp["choices"][0]["message"]["content"].strip()
                if not silent:
                    print(Fore.GREEN + "Grok responded" + Style.RESET_ALL)
                return result
        except Exception as e:
            if not silent:
                print(Fore.YELLOW + f"Grok failed: {e}" + Style.RESET_ALL)
    
    # Fallback to OpenAI
    if openai_client:
        try:
            if not silent:
                print(Fore.BLUE + "Using OpenAI..." + Style.RESET_ALL)
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            result = resp.choices[0].message.content.strip()
            if not silent:
                print(Fore.GREEN + "OpenAI responded" + Style.RESET_ALL)
            return result
        except Exception as e:
            if not silent:
                print(Fore.RED + f"OpenAI failed: {e}" + Style.RESET_ALL)
    return None
