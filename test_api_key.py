#!/usr/bin/env python3
"""
API Key Test Script
===================
Tests if your LLM API key is working correctly.

Usage:
    python test_api_key.py
"""

import os
import sys
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from config import LLMConfig

# Load environment variables
load_dotenv(project_root / ".env")

def test_api_key():
    """Test the LLM API key with a simple request."""

    # Load config
    try:
        config = LLMConfig()
        print("✅ Config loaded successfully")
        print(f"   Model: {config.model}")
        print(f"   Base URL: {config.base_url}")
        print(f"   API Key: {config.api_key[:8]}...{config.api_key[-4:] if len(config.api_key) > 12 else config.api_key}")
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False

    # Determine API format based on base URL
    is_openrouter = "openrouter.ai" in config.base_url
    is_anthropic = "anthropic.com" in config.base_url
    is_openai = "openai.com" in config.base_url or "api.openai.com" in config.base_url

    print(f"\n🔍 Detected API provider: {'OpenRouter' if is_openrouter else 'Anthropic' if is_anthropic else 'OpenAI' if is_openai else 'Unknown'}")

    # Prepare test request
    test_prompt = "Say 'Hello, API key test successful!' and nothing else."

    if is_anthropic:
        # Anthropic Claude format
        payload = {
            "model": config.model,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": test_prompt}],
            "temperature": 0.1
        }
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": config.api_key,
        }
        url = config.base_url

    elif is_openrouter or is_openai:
        # OpenAI/OpenRouter format
        payload = {
            "model": config.model,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": test_prompt}],
            "temperature": 0.1
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        }
        url = config.base_url

    else:
        print(f"❌ Unsupported API provider for URL: {config.base_url}")
        return False

    print("\n🚀 Testing API connection...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"   Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("✅ API call successful!")

            # Extract response text
            if is_anthropic and "content" in data:
                response_text = data["content"][0].get("text", "")
            elif (is_openrouter or is_openai) and "choices" in data:
                response_text = data["choices"][0]["message"]["content"]
            else:
                response_text = str(data)

            print(f"   Response: {response_text.strip()}")

            if "successful" in response_text.lower() or "hello" in response_text.lower():
                print("🎉 API key test PASSED!")
                return True
            else:
                print("⚠️  API responded but with unexpected content")
                return True

        elif response.status_code == 401:
            print("❌ API key is INVALID or EXPIRED")
            print("   Check your LLM_API_KEY in .env file")
        elif response.status_code == 403:
            print("❌ API key FORBIDDEN - insufficient permissions or credits")
            print("   Check your account credits/quota on the provider's website")
        elif response.status_code == 429:
            print("❌ RATE LIMITED - too many requests")
            print("   Wait a few minutes and try again")
        elif response.status_code >= 500:
            print(f"❌ SERVER ERROR ({response.status_code})")
            print("   The API provider is having issues")
        else:
            print(f"❌ HTTP {response.status_code} error")
            try:
                error_data = response.json()
                print(f"   Error details: {error_data}")
            except:
                print(f"   Response: {response.text[:200]}")

        return False

    except requests.exceptions.Timeout:
        print("❌ Request TIMED OUT")
        print("   Check your internet connection")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR")
        print("   Check your internet connection or API URL")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    print("🔑 LLM API Key Test")
    print("=" * 50)

    success = test_api_key()

    print("\n" + "=" * 50)
    if success:
        print("✅ API key appears to be working!")
        print("   The automation should be able to generate comments now.")
    else:
        print("❌ API key test FAILED")
        print("   Check your .env file and API provider account.")
        print("\n🔧 Troubleshooting tips:")
        print("   1. Verify LLM_API_KEY in .env file")
        print("   2. Check API provider account credits/quota")
        print("   3. Confirm LLM_BASE_URL is correct")
        print("   4. Try regenerating your API key")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())