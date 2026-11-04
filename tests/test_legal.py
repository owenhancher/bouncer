from bouncer.legal import PAGES, load_page, savings_note

DRAFT = "DRAFT, not legal advice; have a lawyer review before relying on it."


def test_legal_pages_exist_and_load():
    for fname in PAGES.values():
        text = load_page(fname)
        assert DRAFT in text.splitlines()[0]
        assert "# " in text and "[EFFECTIVE DATE]" in text


def test_savings_note():
    assert savings_note().startswith("Values and savings are estimates")
