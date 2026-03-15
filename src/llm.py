"""
src/llm.py — Streaming LLM service.
Uses async generator so tokens stream to UI immediately.
"""

import os
import re
from typing import AsyncGenerator
from huggingface_hub import InferenceClient

_client: InferenceClient | None = None


def _get_client() -> InferenceClient:
    global _client
    if _client is None:
        token = os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        if not token:
            raise RuntimeError(
                "Add HUGGINGFACEHUB_API_TOKEN=hf_xxx to your .env file."
            )
        _client = InferenceClient(provider="auto", api_key=token)
    return _client


def _strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text)
    return text.strip()


async def ask_order_stream(
    messages: list,
    temperature: float = 0.5,
) -> AsyncGenerator[str, None]:
    """
    Yields response tokens one by one for streaming display.
    Buffers and strips <think> blocks before yielding.
    """
    client = _get_client()

    full_messages = messages.copy()
    if len(full_messages) > 1:
        full_messages.insert(1, {
            "role": "system",
            "content": (
                "Reply directly and concisely. "
                "Do NOT include <think> blocks or internal reasoning."
            ),
        })

    stream = client.chat.completions.create(
        model="Qwen/Qwen3-8B",
        messages=full_messages,
        temperature=max(temperature, 0.01),
        max_tokens=512,
        stream=True,
    )

    # Buffer to catch and suppress <think> blocks mid-stream
    buffer = ""
    inside_think = False

    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if not token:
            continue

        buffer += token

        # Detect opening think tag
        if "<think>" in buffer:
            inside_think = True

        # Detect closing think tag — flush clean text after it
        if inside_think and "</think>" in buffer:
            after = buffer.split("</think>", 1)[1]
            buffer = after
            inside_think = False
            if buffer:
                yield buffer
                buffer = ""
            continue

        # If inside think block, keep buffering (don't yield)
        if inside_think:
            continue

        # Normal token — yield immediately
        yield token
        buffer = ""
