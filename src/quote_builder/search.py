"""Showing where a search matched: highlighted text and excerpts.

Plain text in, HTML out: the text is escaped first, so a description
typed as `<b>Deck</b>` shows as typed, and only our `<mark>` tags are
HTML.
"""

import html
import re

from quote_builder.quotes import QuoteSummary, SearchText, version_name

# Tailwind classes for a match: softer than the browser's bright yellow.
MARK_CLASS = "bg-amber-200 rounded-sm"

# Characters of context kept on each side of a match in an excerpt.
CONTEXT = 20


def _pattern(term: str) -> re.Pattern[str]:
    # re.escape: the term is matched as typed, so `$5.50` or `(` work.
    return re.compile(re.escape(term.strip()), re.IGNORECASE)


def matches(text: str, term: str) -> bool:
    """Whether `text` holds `term`, in any case."""
    return bool(term.strip()) and _pattern(term).search(text) is not None


def highlight(text: str, term: str) -> str:
    """`text` as escaped HTML, each match of `term` wrapped in <mark>."""
    if not term.strip():
        return html.escape(text)
    parts = []
    end = 0
    for found in _pattern(term).finditer(text):
        parts.append(html.escape(text[end : found.start()]))
        parts.append(f'<mark class="{MARK_CLASS}">{html.escape(found.group())}</mark>')
        end = found.end()
    parts.append(html.escape(text[end:]))
    return "".join(parts)


def excerpt(text: str, term: str) -> str:
    """The part of `text` around the first match of `term`, with "…"
    where it was cut, as plain text."""
    found = _pattern(term).search(text)
    if found is None:
        return text
    start = max(0, found.start() - CONTEXT)
    end = min(len(text), found.end() + CONTEXT)
    # Back off to whole words where cut, never into the match itself.
    if start > 0:
        space = text.find(" ", start, found.start())
        start = space + 1 if space != -1 else start
    if end < len(text):
        space = text.rfind(" ", found.end(), end)
        end = space if space != -1 else end
    cut = " ".join(text[start:end].split())  # notes may hold line breaks
    return ("…" if start > 0 else "") + cut + ("…" if end < len(text) else "")


def hidden_match(
    summary: QuoteSummary, texts: list[SearchText], term: str
) -> tuple[str, str] | None:
    """Where `term` matched, when the row doesn't show it, and an
    excerpt: ("Notes", "…back hedges too…"), ("Line Item 3", …), or
    ("R1, Line Item 2", …) for an older version, as plain text.

    None if there's no term, or the row's number or first line shows
    the match already. `texts` is the quote's, newest version first.
    """
    if not term.strip():
        return None
    name = version_name(summary.number, summary.revision)
    if matches(name, term) or matches(summary.first_line or "", term):
        return None
    for piece in texts:
        is_first_line = piece.field == "line" and piece.position == 0
        if piece.revision == summary.revision and is_first_line:
            continue  # shown in the row
        if matches(piece.text, term):
            return _place(piece, summary.revision), excerpt(piece.text, term)
    return None


def _place(piece: SearchText, newest: int) -> str:
    # "Line Item", not "Line" (reads like code) or "Item" (odd for a
    # service).
    where = "Notes" if piece.field == "notes" else f"Line Item {piece.position + 1}"
    if piece.revision == newest:
        return where
    version = f"R{piece.revision}" if piece.revision else "Original"
    return f"{version}, {where}"
