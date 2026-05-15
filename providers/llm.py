# providers/llm.py
import requests
from typing import Optional
import config
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMError(Exception):
    """Exception raised when all LLM providers fail."""
    pass


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate(system_prompt: str, user_prompt: str) -> str:
    """Generate text using LLM. Tries Groq first, falls back to Ollama."""
    if config.LLM_PROVIDER == "groq":
        try:
            return _groq_generate(system_prompt, user_prompt)
        except Exception as e:
            print(f"[LLM] Groq failed: {e}, falling back to Ollama")
            return _ollama_generate(system_prompt, user_prompt)
    else:
        return _ollama_generate(system_prompt, user_prompt)


def _groq_generate(system_prompt: str, user_prompt: str) -> str:
    """Generate using Groq SDK."""
    if not config.GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY not set")

    client = Groq(api_key=config.GROQ_API_KEY)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    print("[LLM] Using groq")
    return response.choices[0].message.content


def _ollama_generate(system_prompt: str, user_prompt: str) -> str:
    """Generate using Ollama API."""
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
        "stream": True
    }
    response = requests.post(url, json=payload, timeout=120)
    if response.status_code != 200:
        raise LLMError(f"Ollama returned status {response.status_code}")

    full_text = ""
    for line in response.iter_lines():
        if line:
            data = line.decode("utf-8")
            if data.startswith("{"):
                import json
                chunk = json.loads(data)
                if "response" in chunk:
                    full_text += chunk["response"]

    print("[LLM] Falling back to ollama")
    return full_text.strip()