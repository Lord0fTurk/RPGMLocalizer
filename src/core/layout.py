from __future__ import annotations

import re

from .text_segmenter import _CODE_RE


def measure(text: str) -> int:
    return len(_CODE_RE.sub("", text))


def chop(word: str, width: int) -> list[str]:
    if measure(word) <= width:
        return [word]
    pieces: list[str] = []
    piece = ""
    used = 0
    at = 0
    while at < len(word):
        m = _CODE_RE.match(word, at)
        if m:
            take = m.group(0)
            cost = 0
        else:
            take = word[at]
            cost = 1
        if used + cost > width and piece:
            pieces.append(piece)
            piece = ""
            used = 0
        piece += take
        used += cost
        at += len(take)
    if piece:
        pieces.append(piece)
    return pieces


def wrap(text: str, width: int) -> list[str]:
    if not text:
        return []
    rows: list[str] = []
    row = ""
    for word in text.split():
        for piece in chop(word, width):
            if not row:
                row = piece
                continue
            if measure(row) + 1 + measure(piece) <= width:
                row += " " + piece
            else:
                rows.append(row)
                row = piece
    if row:
        rows.append(row)
    return rows


def reflow_text(text: str, width: int) -> str:
    if not text or width <= 0:
        return text
    if _CODE_RE.sub("", text).strip() == "":
        return text
    if measure(text) <= width:
        return text
    lines = wrap(text, width)
    if not lines:
        return text
    return "\n".join(lines)
