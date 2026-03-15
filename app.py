"""
Zomato OrderBot — app.py
Fast, simple, streaming responses.
"""

import chainlit as cl
import chainlit.data as cl_data

from src.llm import ask_order_stream
from src.image_service import detect_and_fetch_images
from src.history import HistoryDataLayer
from src.prompt import system_instruction

# ── Simple local history ──
cl_data._data_layer = HistoryDataLayer()


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set(
        "messages",
        [{"role": "system", "content": system_instruction}],
    )
    await cl.Message(
        content=(
            "👋 **Welcome to Zomato OrderBot!**\n\n"
            "I'm your personal food ordering assistant. "
            "Tell me what you'd like to order! 🍕🍜🍛"
        ),
        author="Zomato OrderBot",
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    messages: list = cl.user_session.get("messages")
    messages.append({"role": "user", "content": message.content})

    # Stream response token by token for fast perceived response
    response_msg = cl.Message(content="", author="Zomato OrderBot")
    full_text = ""

    async for token in ask_order_stream(messages):
        full_text += token
        await response_msg.stream_token(token)

    # Detect food images from full response
    image_elements = await detect_and_fetch_images(full_text)
    response_msg.elements = image_elements

    await response_msg.send()

    messages.append({"role": "assistant", "content": full_text})
    cl.user_session.set("messages", messages)
