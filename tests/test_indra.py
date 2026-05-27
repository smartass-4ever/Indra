"""Tests for the Indra web intelligence layer."""

import os
import tempfile
import pytest

from indra.web.change_detector import (
    fingerprint, has_changed, extract_diff, summarise_change, build_change_prompt,
)
from indra.web.store import WebSnapshotStore


# ── change_detector ───────────────────────────────────────────────────────────

def test_fingerprint_is_deterministic():
    assert fingerprint("hello") == fingerprint("hello")

def test_fingerprint_differs_on_change():
    assert fingerprint("price: $49") != fingerprint("price: $39")

def test_has_changed_true():
    assert has_changed("abc", "xyz") is True

def test_has_changed_false():
    assert has_changed("abc", "abc") is False

def test_extract_diff_detects_text_change():
    old = "<html><body>Price: $49.99</body></html>"
    new = "<html><body>Price: $39.99</body></html>"
    diff = extract_diff(old, new)
    assert "$49.99" in diff or "$39.99" in diff

def test_extract_diff_no_change():
    content = "<html><body>Same content</body></html>"
    diff = extract_diff(content, content)
    assert "Minor change" in diff or diff == ""

def test_summarise_change_counts_lines():
    old = "line1\nline2\nline3"
    new = "line1\nline2\nline4"
    summary = summarise_change(old, new)
    assert "line" in summary.lower() or "+" in summary or "-" in summary

def test_build_change_prompt_contains_url_and_question():
    prompt = build_change_prompt("https://example.com", "- old\n+ new", "Did prices change?")
    assert "https://example.com" in prompt
    assert "Did prices change?" in prompt
    assert "- old" in prompt or "+ new" in prompt


# ── WebSnapshotStore ──────────────────────────────────────────────────────────

@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = WebSnapshotStore(db_path=path)
    s.connect()
    yield s
    s.close()
    os.unlink(path)

def test_store_get_missing(store):
    assert store.get("https://nothere.com") is None

def test_store_upsert_and_get(store):
    store.upsert("https://example.com", "hash1", "content1", changed=False)
    row = store.get("https://example.com")
    assert row is not None
    assert row["hash"] == "hash1"
    assert row["change_count"] == 0

def test_store_change_increments_count(store):
    store.upsert("https://example.com", "hash1", "content1", changed=False)
    store.upsert("https://example.com", "hash2", "content2", changed=True)
    row = store.get("https://example.com")
    assert row["change_count"] == 1
    assert row["hash"] == "hash2"

def test_store_set_insight(store):
    store.upsert("https://example.com", "hash1", "content1", changed=False)
    store.set_insight("https://example.com", "prices dropped 20%")
    row = store.get("https://example.com")
    assert row["last_insight"] == "prices dropped 20%"

def test_store_insight_survives_upsert(store):
    store.upsert("https://example.com", "hash1", "content1", changed=False)
    store.set_insight("https://example.com", "cached insight")
    store.upsert("https://example.com", "hash1", "content1", changed=False)
    row = store.get("https://example.com")
    assert row["last_insight"] == "cached insight"
