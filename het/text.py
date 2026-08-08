"""Small text helpers shared by adapters."""

from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</(p|div|li|tr|h[1-6])>|<br\s*/?>", re.I)


def strip_html(value: str | None) -> str | None:
    """Turn an HTML fragment into plain text.

    Several sources put markup inside fields that are nominally plain text, so
    adapters run everything user-visible through this.
    """
    if not value:
        return value
    text = _BLOCK_END.sub("\n", value)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()
