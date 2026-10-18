"""Quote numbers: `Q-` and a random code shaped like a phone number."""

import secrets

# Crockford's Base32: no I, L, O, or U, which are easy to misread.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_quote_number() -> str:
    """A new random quote number, such as `Q-7KQ-M9XD`.

    Not checked for uniqueness: the database refuses a number already
    used, and the caller draws again.
    """
    code = "".join(secrets.choice(ALPHABET) for _ in range(7))
    return f"Q-{code[:3]}-{code[3:]}"
