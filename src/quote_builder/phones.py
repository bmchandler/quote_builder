"""Reading and showing phone numbers typed by the user.

A number is stored as its ten digits (`1234567890`) and shown in the
standard form `(123) 456-7890`, so storage and display stay decoupled:
the stored digits never change if the shown form later does, and a
search matches by digits however either side is punctuated. An
extension is kept apart, digits only.
"""

import re

_NON_DIGIT = re.compile(r"\D")


def digits(text: str) -> str:
    """Just the digits of `text`: `(123) 456-7890` gives `1234567890`."""
    return _NON_DIGIT.sub("", text)


def parse_phone(text: str) -> str:
    """The ten digits of a phone number entered as `1234567890`,
    `123.456.7890`, `(123) 456-7890`, and the like; blank for blank.

    Raises ValueError, with a message for the user, for anything that
    isn't ten digits (the intended user base is US only).
    """
    cleaned = text.strip()
    if not cleaned:
        return ""
    found = digits(cleaned)
    if len(found) != 10:
        raise ValueError(f"{cleaned!r} isn't a 10-digit phone number")
    return found


def parse_ext(text: str) -> str:
    """An extension, digits only such as `12`; blank for blank.

    Raises ValueError, with a message for the user, for anything else.
    """
    cleaned = text.strip()
    if not cleaned:
        return ""
    if not cleaned.isdigit():
        raise ValueError(f"{cleaned!r} isn't an extension")
    return cleaned


def format_phone(stored: str) -> str:
    """`(123) 456-7890` from ten stored digits; `stored` unchanged if it
    isn't ten digits, so odd or older data still shows."""
    if len(stored) == 10 and stored.isdigit():
        return f"({stored[:3]}) {stored[3:6]}-{stored[6:]}"
    return stored


def format_phone_ext(stored: str, ext: str) -> str:
    """The phone with its extension, `(123) 456-7890 ext. 12`; either
    part may be blank."""
    shown = format_phone(stored)
    if ext:
        return f"{shown} ext. {ext}".strip()
    return shown


def phone_matches(phone: str, term: str) -> bool:
    """Whether `term`'s digits appear in `phone`'s, so a search finds a
    number however either side is punctuated. False when `term` holds no
    digit, so a text search doesn't light up every number."""
    found = digits(term)
    return bool(found) and found in digits(phone)
