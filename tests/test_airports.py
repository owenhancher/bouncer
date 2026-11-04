from bouncer.airports import get, label_for, picker_options, search


def codes(q, n=20):
    return [a.iata for a in search(q, n)]


def test_new_york_returns_all_three():
    assert {"JFK", "LGA", "EWR"} <= set(codes("new york"))


def test_lon_returns_lhr():
    assert "LHR" in codes("lon")


def test_exact_code_first():
    assert codes("jfk")[0] == "JFK"
    assert codes("LHR")[0] == "LHR"


def test_airport_name_search():
    assert "LHR" in codes("heathrow")


def test_labels_and_options():
    assert label_for("JFK").startswith("New York, US: JFK")
    assert "New York area" in label_for("EWR")
    assert label_for("ZZZ") == "ZZZ"
    opts = picker_options()
    assert "JFK" in opts and "LHR" in opts and len(opts) == len(set(opts))
    assert get("jfk").iata == "JFK"


def test_empty_query():
    assert search("") == []
