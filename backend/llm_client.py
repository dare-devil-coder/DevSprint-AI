# One shared OpenAI client and validated JSON generation helpers.
"""One shared OpenAI client and validated JSON generation helpers."""

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Create the asynchronous OpenAI client once, on first use."""
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or key == "your_openai_key_here":
            raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env to run generation.")
        _client = AsyncOpenAI(api_key=key)
    return _client


async def generate_json(system: str, user: str) -> dict[str, Any]:
    """Request one JSON object and reject malformed model output."""
    response = await get_client().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("OpenAI returned an empty response.")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("OpenAI must return a JSON object.")
    return data
