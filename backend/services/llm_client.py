import os
import json
from openai import OpenAI
import anthropic


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "groq").lower()


def _call_groq(prompt: str, max_tokens: int = 4096) -> str:
    client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(prompt: str, max_tokens: int = 4096) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def llm_call(prompt: str, max_tokens: int = 1500) -> str:
    provider = get_provider()
    if provider == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    else:
        return _call_groq(prompt, max_tokens)


def parse_json_response(raw: str) -> any:
    import re
    text = raw.strip()
    # Strip thinking tags (Qwen3 etc.)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            if part.startswith("json"):
                text = part[4:].strip()
                break
            elif i % 2 == 1:
                text = part.strip()
                break
    text = text.strip()
    # Try clean parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Recovery: truncated JSON array — salvage complete items
    if text.startswith("["):
        # Find last complete object by scanning for }
        depth = 0
        last_good = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    last_good = i + 1
        if last_good > 0:
            recovered = text[:last_good] + "]"
            try:
                return json.loads(recovered)
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Could not parse JSON response: {text[:200]}")
