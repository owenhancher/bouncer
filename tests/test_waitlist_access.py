from pathlib import Path

from bouncer.access import can_run_live, live_cap, live_unlocked
from bouncer.waitlist import add_entry, validate_email


def test_email_validation():
    ok, _ = validate_email("not-an-email")
    assert not ok
    ok, norm = validate_email("  You@Example.COM ")
    assert ok and norm == "you@example.com"


def test_waitlist_dedupe(tmp_path):
    p = tmp_path / "wl.csv"
    ok, msg = add_entry("a@b.co", "JFK", path=p)
    assert ok and p.exists()
    ok2, msg2 = add_entry("A@B.CO", "LGA", path=p)
    assert ok2 and "already" in msg2.lower()
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2  # header + 1


def test_live_gated_without_code():
    env = {"BOUNCER_LIVE_CODE": "", "BOUNCER_LIVE_SEARCH_CAP": "3"}
    assert live_unlocked("secret", env) is False
    ok, msg = can_run_live("secret", 0, env)
    assert not ok


def test_live_cap_enforced():
    env = {"BOUNCER_LIVE_CODE": "letmein", "BOUNCER_LIVE_SEARCH_CAP": "2"}
    assert live_unlocked("letmein", env)
    ok, _ = can_run_live("letmein", 0, env)
    assert ok
    ok2, msg = can_run_live("letmein", 2, env)
    assert not ok2 and "limit" in msg.lower()
    assert live_cap(env) == 2
