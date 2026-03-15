import os
import re
from huggingface_hub import InferenceClient
from src.prompt import system_instruction

HF_TOKEN = os.environ.get("HUGGINGFACEHUB_API_TOKEN")

if not HF_TOKEN:
    raise RuntimeError(
        "Missing HuggingFace token. Add HUGGINGFACEHUB_API_TOKEN=hf_xxx to your .env file."
    )

client = InferenceClient(
    provider="auto", # Automatically select the best model provider (HuggingFace or Azure OpenAI) based on the model name
    api_key=HF_TOKEN,
)

messages = [
    {"role": "system", "content": system_instruction}
]


def _strip_thinking(text):
    """Remove <think>...</think> blocks including any text before the first clean line."""
    # Remove <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove any leftover </think> or <think> tags
    text = re.sub(r"</?think>", "", text)
    return text.strip()


def ask_order(messages, temperature=0.5):
    # Add instruction to not think out loud
    full_messages = messages.copy()
    full_messages.insert(1, {
        "role": "system",
        "content": "Do NOT include any thinking, reasoning, or <think> tags in your response. Reply directly and concisely."
    })

    response = client.chat.completions.create(
        model="Qwen/Qwen3-8B",
        messages=full_messages,
        temperature=max(temperature, 0.01),
        max_tokens=512,
    )

    raw = response.choices[0].message.content
    return _strip_thinking(raw)
    