"""
src/image_service.py
Returns food images that EXACTLY match what the user ordered.
Strict word-boundary matching — pizza won't show burger.
"""

import re
from typing import List
import chainlit as cl

# ── Exact food item → Unsplash image ──
FOOD_IMAGES: dict[str, str] = {
    # Pizzas
    "cheese pizza":        "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=320&q=80",
    "pepperoni pizza":     "https://images.unsplash.com/photo-1628840042765-356cda07504e?w=320&q=80",
    "hawaiian pizza":      "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=320&q=80",
    "veggie pizza":        "https://images.unsplash.com/photo-1541745537411-b8046dc6d66c?w=320&q=80",
    "meat lovers pizza":   "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=320&q=80",
    "margherita pizza":    "https://images.unsplash.com/photo-1604382354936-07c5d9983bd3?w=320&q=80",
    "pizza":               "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=320&q=80",

    # Pasta & Noodles
    "spaghetti and meatballs": "https://images.unsplash.com/photo-1555949258-eb67b1ef0ceb?w=320&q=80",
    "lasagna":             "https://images.unsplash.com/photo-1574894709920-11b28e7367e3?w=320&q=80",
    "macaroni and cheese": "https://images.unsplash.com/photo-1543339308-43e59d6b73a6?w=320&q=80",
    "chicken and broccoli pasta": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=320&q=80",
    "chow mein":           "https://images.unsplash.com/photo-1563245372-f21724e3856d?w=320&q=80",
    "pasta":               "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=320&q=80",

    # Asian
    "chicken fried rice":  "https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=320&q=80",
    "sushi platter":       "https://images.unsplash.com/photo-1617196034183-421b4040ed20?w=320&q=80",
    "sushi":               "https://images.unsplash.com/photo-1559410545-0bdcd187e0a6?w=320&q=80",
    "curry chicken with rice": "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=320&q=80",

    # Indian
    "butter chicken":      "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=320&q=80",
    "chicken tikka masala": "https://images.unsplash.com/photo-1588166524941-3bf61a9c41db?w=320&q=80",
    "palak paneer":        "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?w=320&q=80",
    "chana masala":        "https://images.unsplash.com/photo-1589647363585-f4a7d3877b10?w=320&q=80",
    "vegetable biryani":   "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=320&q=80",
    "biryani":             "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=320&q=80",
    "samosa":              "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=320&q=80",
    "lassi":               "https://images.unsplash.com/photo-1571091718767-18b5b1457add?w=320&q=80",

    # Beverages
    "milkshake":           "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=320&q=80",
    "mango smoothie":      "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=320&q=80",
    "berry smoothie":      "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=320&q=80",
    "banana smoothie":     "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=320&q=80",
    "smoothie":            "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=320&q=80",
    "coffee":              "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=320&q=80",
    "hot tea":             "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=320&q=80",
    "juice box":           "https://images.unsplash.com/photo-1622597467836-f3285f2131b8?w=320&q=80",
    "coke":                "https://images.unsplash.com/photo-1554866585-cd94860890b7?w=320&q=80",
    "sprite":              "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?w=320&q=80",
    "water bottle":        "https://images.unsplash.com/photo-1548839140-29a749e1cf4d?w=320&q=80",
}

# Sort longest first so "pepperoni pizza" matches before "pizza"
_SORTED_KEYS = sorted(FOOD_IMAGES.keys(), key=len, reverse=True)


async def detect_and_fetch_images(text: str) -> List[cl.Image]:
    """
    Strictly match food keywords in bot response.
    Once a specific item matches (e.g. 'pepperoni pizza'),
    the generic fallback ('pizza') is skipped to avoid duplicates.
    Returns at most 3 images.
    """
    lower = text.lower()
    seen_urls: set[str] = set()
    matched_words: set[str] = set()   # track which words already matched
    elements: List[cl.Image] = []

    for keyword in _SORTED_KEYS:
        if len(elements) >= 3:
            break

        # Strict full-phrase word-boundary match
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if not re.search(pattern, lower):
            continue

        # Skip generic fallback if a specific version already matched
        # e.g. skip "pizza" if "pepperoni pizza" already matched
        keyword_words = set(keyword.split())
        if keyword_words & matched_words:
            continue

        url = FOOD_IMAGES[keyword]
        if url in seen_urls:
            continue

        seen_urls.add(url)
        matched_words.update(keyword_words)
        elements.append(
            cl.Image(
                url=url,
                name=keyword.title(),
                display="inline",
            )
        )

    return elements
