"""Paragraphs are presentation, independent of audio request boundaries."""

import re


def format_paragraphs(text, target_chars=500):
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        current = []
        length = 0
        for sentence in sentences:
            if current and length >= target_chars:
                paragraphs.append(" ".join(current))
                current, length = [], 0
            current.append(sentence)
            length += len(sentence) + 1
        if current:
            paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)
