"""
Content fingerprinting and change detection for Indra.

Core logic: hash the fetched content, compare to the stored hash.
If hashes differ, extract a compact diff for the LLM — so the LLM
reasons only over what changed, not the full page.
"""

import difflib
import hashlib
import re
from typing import Optional, Tuple


def fingerprint(content: str) -> str:
    """SHA-256 hash of content, truncated to 32 hex chars."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:32]


def has_changed(old_hash: str, new_hash: str) -> bool:
    return old_hash != new_hash


def extract_diff(old_content: str, new_content: str, max_lines: int = 80) -> str:
    """
    Return a unified diff of old vs new content, capped at max_lines.
    Strips HTML tags first so diffs reflect semantic text changes, not markup churn.
    """
    old_text = _strip_html(old_content)
    new_text = _strip_html(new_content)

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile="previous", tofile="current",
        n=3,
    ))

    if not diff:
        # Structural change (whitespace/markup only) — return short summary
        return f"[Minor change detected — {abs(len(new_text) - len(old_text))} chars difference]"

    return "".join(diff[:max_lines])


def summarise_change(old_content: str, new_content: str) -> str:
    """
    One-line human-readable summary of the change magnitude.
    Used in prompts and the savings dashboard.
    """
    old_text = _strip_html(old_content)
    new_text = _strip_html(new_content)

    added, removed = 0, 0
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1

    if added == 0 and removed == 0:
        return "whitespace/markup change only"
    parts = []
    if added:
        parts.append(f"+{added} lines")
    if removed:
        parts.append(f"-{removed} lines")
    return ", ".join(parts)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace for cleaner diffs."""
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_change_prompt(url: str, diff: str, question: str) -> str:
    """
    Build a tight LLM prompt that focuses only on what changed.
    The LLM never sees the full page — only the delta.
    """
    return (
        f"You are a web monitoring assistant. Reply with plain English only — "
        f"no JSON, no code blocks, no bullet points, no 'position' fields. "
        f"Write exactly 1-2 sentences answering the question based on the diff.\n\n"
        f"URL: {url}\n\n"
        f"Diff:\n```\n{diff}\n```\n\n"
        f"Question: {question}\n\n"
        f"Answer (1-2 plain sentences):"
    )
