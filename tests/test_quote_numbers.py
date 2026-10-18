import re

from quote_builder.quote_numbers import ALPHABET, new_quote_number


def test_alphabet_is_crockford_base32():
    assert ALPHABET == "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def test_quote_number_is_shaped_like_a_phone_number():
    pattern = re.compile(rf"Q-[{ALPHABET}]{{3}}-[{ALPHABET}]{{4}}")
    for _ in range(1000):
        assert pattern.fullmatch(new_quote_number())


def test_quote_numbers_use_the_whole_alphabet():
    # 14,000 characters drawn: the odds of missing any one are negligible.
    seen = {c for _ in range(2000) for c in new_quote_number()[2:]}
    assert seen - {"-"} == set(ALPHABET)
