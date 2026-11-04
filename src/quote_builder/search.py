"""Showing where a search matched: highlighted text and excerpts.

Plain text in, HTML out: the text is escaped first, so a description
typed as `<b>Deck</b>` shows as typed, and only our `<mark>` tags are
HTML.
"""

import html
import re
from typing import NamedTuple

from quote_builder.phones import digits, format_phone, phone_matches
from quote_builder.quotes import QuoteSummary, SearchText, version_name

# The phone's place among a customer's details (storage.CUSTOMER_DETAILS):
# name, email, phone, address. It's stored as digits and matched by them.
_PHONE_DETAIL = 2

# A phone in the standard form, to find within a customer's joined
# details so its digit matches can be highlighted (see highlight_phone).
_SHOWN_PHONE = re.compile(r"\(\d{3}\) \d{3}-\d{4}")

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


def highlight_phone(shown: str, term: str) -> str:
    """A phone in the standard form as escaped HTML, the run matching
    `term`'s digits wrapped in one <mark>, separators within it included.

    So `4567890` highlights `456-7890`, not nothing: the digits aren't
    next to each other in the shown form, but map onto one span of it.
    """
    wanted = digits(term)
    pool = digits(shown)
    if not wanted or wanted not in pool:
        return html.escape(shown)
    first = pool.index(wanted)
    at = [i for i, char in enumerate(shown) if char.isdigit()]
    start, end = at[first], at[first + len(wanted) - 1] + 1
    marked = f'<mark class="{MARK_CLASS}">{html.escape(shown[start:end])}</mark>'
    return html.escape(shown[:start]) + marked + html.escape(shown[end:])


def highlight_details(details: str, term: str) -> str:
    """A customer's joined details as escaped HTML: the phone part
    highlighted by its digits (highlight_phone), the rest as typed."""
    found = _SHOWN_PHONE.search(details)
    if found is None:
        return highlight(details, term)
    before, phone, after = (
        details[: found.start()],
        found.group(),
        details[found.end() :],
    )
    return highlight(before, term) + highlight_phone(phone, term) + highlight(after, term)


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


def row_text(summary: QuoteSummary) -> str | None:
    """The row's second line: its customer's name, or without one, its
    first line's description (None if it has no lines)."""
    return summary.customer_name or summary.first_line


class HiddenMatch(NamedTuple):
    """A match the quote's row doesn't show."""

    place: str  # "Notes", "Line Item 3", "R1, Line Item 2"
    excerpt: str  # plain text
    revision: int  # the version it's in
    is_phone: bool = False  # a phone, so highlight its digits, not literally


def hidden_match(
    summary: QuoteSummary, texts: list[SearchText], term: str
) -> HiddenMatch | None:
    """Where `term` matched, when the row doesn't show it, an excerpt,
    and the version: the newest that matched.

    None if there's no term, or the row's number or second line shows
    the match already. `texts` is the quote's, newest version first.
    """
    if not term.strip():
        return None
    name = version_name(summary.number, summary.revision)
    if matches(name, term) or matches(row_text(summary) or "", term):
        return None
    shows_first_line = summary.customer_name is None
    for piece in texts:
        is_first_line = piece.field == "line" and piece.position == 0
        if piece.revision == summary.revision and is_first_line and shows_first_line:
            continue  # shown in the row
        if _piece_matches(piece, term):
            return HiddenMatch(
                _place(piece, summary.revision),
                _piece_excerpt(piece, term),
                piece.revision,
                is_phone=_is_phone(piece),
            )
    return None


def _is_phone(piece: SearchText) -> bool:
    return piece.field == "customer" and piece.position == _PHONE_DETAIL


def _piece_matches(piece: SearchText, term: str) -> bool:
    """A phone matches by digits; everything else as typed."""
    if _is_phone(piece):
        return phone_matches(piece.text, term)
    return matches(piece.text, term)


def _piece_excerpt(piece: SearchText, term: str) -> str:
    """A phone shows formatted (short enough to show whole); everything
    else as an excerpt around the match."""
    if _is_phone(piece):
        return format_phone(piece.text)
    return excerpt(piece.text, term)


def _place(piece: SearchText, newest: int) -> str:
    # "Line Item", not "Line" (reads like code) or "Item" (odd for a
    # service).
    if piece.field == "customer":
        where = "Customer"
    elif piece.field == "notes":
        where = "Notes"
    else:
        where = f"Line Item {piece.position + 1}"
    if piece.revision == newest:
        return where
    version = f"R{piece.revision}" if piece.revision else "Original"
    return f"{version}, {where}"
