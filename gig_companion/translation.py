"""Cross-lingual helpers: translate queries to English for retrieval and answers back.

URLs are swapped for placeholders before translation and restored afterwards, so
official links (e.g. https://eshram.gov.in) always stay in English and unmodified.
"""

from __future__ import annotations

import re

from .config import language_name
from .llm import LLMClient, LLMUnavailableError
from .prompts import TRANSLATE_TEMPLATE, TRANSLATOR_SYSTEM

_URL_RE = re.compile(r"https?://[^\s)\]]+|\b(?:[\w-]+\.)+(?:gov|nic)\.in\b[^\s)\]]*")
_TRAILING_PUNCT = ".,;:!?"


def protect_urls(text: str) -> tuple[str, list[str]]:
    """Replace URLs with ⟦n⟧ placeholders. Returns (protected_text, urls)."""
    urls: list[str] = []

    def _swap(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trailing = url[-1] + trailing
            url = url[:-1]
        urls.append(url)
        return f"⟦{len(urls) - 1}⟧{trailing}"

    return _URL_RE.sub(_swap, text), urls


def restore_urls(text: str, urls: list[str]) -> str:
    """Put URLs back. Any placeholder the model dropped is appended so no link is lost."""
    missing: list[str] = []
    for index, url in enumerate(urls):
        token = f"⟦{index}⟧"
        if token in text:
            text = text.replace(token, url)
        else:
            missing.append(url)
    if missing:
        text = text.rstrip() + "\n" + "\n".join(missing)
    return text


def _translate(text: str, target_code: str, llm: LLMClient) -> str:
    protected, urls = protect_urls(text)
    prompt = TRANSLATE_TEMPLATE.format(target=language_name(target_code), text=protected)
    try:
        translated = llm.generate(prompt, system=TRANSLATOR_SYSTEM, temperature=0.0)
    except LLMUnavailableError:
        return text  # Graceful degradation: show the verified English text.
    return restore_urls(translated.strip(), urls)


def translate(text: str, target_lang: str, llm: LLMClient) -> str:
    """Translate English text into the worker's language (no-op for English)."""
    if target_lang == "en" or not text.strip():
        return text
    return _translate(text, target_lang, llm)


def to_english(text: str, source_lang: str, llm: LLMClient) -> str:
    """Translate a worker's query into English for retrieval (no-op for English)."""
    if source_lang == "en" or not text.strip():
        return text
    return _translate(text, "en", llm)
