import re

from bouncer.legal import PAGES, load_page, savings_note


def test_legal_pages_exist_load_and_are_filled_in():
    for fname in PAGES.values():
        text = load_page(fname)
        assert "# " in text
        assert "DRAFT" not in text
        assert "Bouncer Travel" in text or "bouncertravel@gmail.com" in text
        assert not re.search(r"\[[A-Z][A-Z /,.]+\]", text), f"placeholder left in {fname}"


def test_savings_note():
    assert savings_note().startswith("Values and savings are estimates")
