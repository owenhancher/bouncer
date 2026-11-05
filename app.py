"""Bouncer – interactive travel deal agent (Streamlit UI).

Run with: streamlit run app.py
"""

import os
from datetime import date, timedelta
from typing import List, Optional

import streamlit as st

from bouncer.access import can_run_live, live_cap, live_code, live_unlocked
from bouncer.advice import (
    AdviceItem,
    best_summary,
    cabin_label,
    method_label,
    money,
    rank_with_advice,
    split_flights_hotels,
)
from bouncer.agent import Bouncer
from bouncer.airports import get, label_for, search as search_airports
from bouncer.legal import PAGES as LEGAL_PAGES, load_page, savings_note
from bouncer.live_providers import build_providers_from_env
from bouncer.models import CabinClass, TravelType, TripRequest
from bouncer.tracker import BalanceTracker
from bouncer.transfers import CAVEATS, load_partners
from bouncer.waitlist import add_entry

st.set_page_config(
    page_title="Bouncer · Only real deals get in.",
    page_icon="assets/bouncer-favicon.png",
    layout="wide",
    initial_sidebar_state="auto",
)

INK, VELVET, PAPER = "#14161B", "#B3243A", "#F5F1E8"

st.markdown(
    f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
  #MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stDecoration"] {{ visibility: hidden; height: 0; }}
  /* Keep the header chrome that holds the sidebar toggle; hide only deploy/status bits */
  [data-testid="stToolbar"] {{ display: flex !important; background: transparent; }}
  [data-testid="stToolbar"] [data-testid="stToolbarActions"] {{ display: none; }}
  .block-container {{ padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }}
  h1, h2, h3, h4, .bx-hero h1 {{ font-family: 'Space Grotesk', sans-serif !important; font-weight: 700 !important;
      color: {INK}; letter-spacing: -0.01em; }}
  .bx-hero {{ background: {INK}; color: {PAPER}; border-radius: 18px; padding: 28px 32px; margin-bottom: 1.25rem;
      display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }}
  .bx-hero img {{ height: 56px; }}
  .bx-hero h1 {{ color: {PAPER} !important; font-size: 2.1rem; margin: 0; padding: 0; }}
  .bx-hero p {{ color: #D9D3C7; margin: 6px 0 0; font-size: 1.02rem; max-width: 640px; }}
  .bx-hero .bx-accent {{ color: #E8697C; }}
  [data-testid="stVerticalBlockBorderWrapper"] {{ background: #FFFDF8; border-radius: 14px !important;
      border-color: #E2DACB !important; box-shadow: 0 1px 2px rgba(20,22,27,.04); }}
  .bx-badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .8rem; font-weight: 700;
      font-family: 'Space Grotesk', sans-serif; }}
  .bx-good {{ background: #1F6B3A; color: #fff; }}
  .bx-fair {{ background: #8A5A00; color: #fff; }}
  .bx-skip {{ background: {VELVET}; color: #fff; }}
  .bx-unknown {{ background: #DDD5C5; color: {INK}; }}
  .bx-muted {{ color: #55585F; font-size: .88rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
  .bx-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin: 6px 0 18px; }}
  .bx-card {{ background: #FFFDF8; border: 1px solid #E2DACB; border-radius: 14px; padding: 14px 16px;
      box-shadow: 0 1px 2px rgba(20,22,27,.04); overflow-wrap: anywhere; }}
  .bx-card h5 {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; margin: 0 0 4px; font-size: 1.02rem; color: {INK}; }}
  .bx-card .bx-big {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.35rem; color: {VELVET}; }}
  .bx-card p {{ margin: 2px 0; font-size: .92rem; }}
  .bx-card a {{ color: {VELVET}; font-weight: 600; text-decoration: none; }}
  .bx-step {{ background: #FFFDF8; border: 1px solid #E2DACB; border-radius: 14px; padding: 16px 18px; }}
  .bx-step .bx-num {{ display: inline-flex; width: 28px; height: 28px; border-radius: 50%; background: {VELVET}; color: #fff;
      align-items: center; justify-content: center; font-weight: 700; font-family: 'Space Grotesk', sans-serif; margin-bottom: 6px; }}
  .bx-empty {{ border: 1.5px dashed #D3C9B6; border-radius: 14px; padding: 22px; text-align: center; color: #55585F; }}
  .bx-footer {{ border-top: 1px solid #E2DACB; margin-top: 2.5rem; padding-top: 1rem; display: flex; justify-content: space-between;
      flex-wrap: wrap; gap: 8px; color: #55585F; font-size: .88rem; }}
  .bx-footer b {{ color: {INK}; font-family: 'Space Grotesk', sans-serif; }}
  @media (max-width: 640px) {{
    .block-container {{ padding: 1rem 0.9rem 2rem; }}
    .bx-hero {{ padding: 20px; gap: 14px; }}
    .bx-hero img {{ height: 38px; }}
    .bx-hero h1 {{ font-size: 1.55rem; }}
    .stTabs [data-baseweb="tab-list"] {{ overflow-x: auto; }}
    .stTabs [data-baseweb="tab"] {{ font-size: .9rem; white-space: nowrap; }}
    [data-testid="stMetricValue"] {{ font-size: 1.5rem; }}
  }}
  .stTabs [data-baseweb="tab"] {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.02rem; }}
</style>
""",
    unsafe_allow_html=True,
)



st.logo("assets/bouncer-lockup-horizontal.svg", icon_image="assets/bouncer-mark.svg", size="large")


def _svg_data_uri(path: str) -> str:
    import base64
    from pathlib import Path as _P

    return "data:image/svg+xml;base64," + base64.b64encode(_P(path).read_bytes()).decode()


def _waitlist_form(key: str) -> None:
    with st.form(f"waitlist_{key}"):
        c1, c2 = st.columns([2, 1])
        email = c1.text_input("Email", placeholder="you@example.com", label_visibility="collapsed")
        home = c2.text_input("Home airport (optional)", placeholder="JFK", label_visibility="collapsed")
        if st.form_submit_button("Get early access", type="primary"):
            ok, msg = add_entry(email, home)
            (st.success if ok else st.error)(msg)


def _seed_demo_balances(tracker: BalanceTracker) -> None:
    tracker.set_balance("Chase Ultimate Rewards", 80000, transferable=True)
    tracker.set_balance("Amex Membership Rewards", 60000, transferable=True)
    tracker.set_balance("United MileagePlus", 12000, transferable=False)
    tracker.set_balance("World of Hyatt", 8000, transferable=False)
    tracker.set_balance("Marriott Bonvoy", 25000, transferable=False)


def _render_balances(bouncer: Bouncer, form_key: str) -> None:
    if st.session_state.get("demo_balances"):
        st.caption("Example balances (demo) — edit or replace them.")
    bals = bouncer.tracker.get_all()
    if bals:
        for bal in bals:
            kind = "transferable" if bal.transferable else "loyalty"
            st.write(f"**{bal.program}** · {bal.balance:,} · {kind}")
    else:
        st.info("No balances yet. Add yours, or try example balances.")
        if st.button("Try example balances", key=f"demo_{form_key}"):
            _seed_demo_balances(bouncer.tracker)
            st.session_state.demo_balances = True
            st.rerun()
    with st.form(f"bal_{form_key}"):
        prog = st.text_input("Program", placeholder="Chase Ultimate Rewards")
        amt = st.number_input("Balance", min_value=0, value=10000, step=1000)
        transferable = st.checkbox("Transferable credit-card points", value=True)
        if st.form_submit_button("Save"):
            if prog.strip():
                bouncer.update_balance(prog.strip(), int(amt), transferable=transferable)
                st.session_state.demo_balances = False
                st.success(f"Saved {prog.strip()}: {amt:,}")
                st.rerun()


def _airport_picker(label: str, query_key: str, default_code: str, help_text: str) -> str:
    q = st.text_input(f"{label} city or code", key=query_key,
                      placeholder="e.g. new york, JFK, heathrow", help=help_text)
    matches = search_airports(q, 12) if (q or "").strip() else []
    if not matches:
        pref = get(default_code)
        matches = [pref] if pref else search_airports(default_code, 5)
    codes = [a.iata for a in matches]
    idx = codes.index(default_code) if default_code in codes else 0
    return st.selectbox(label, options=codes, index=idx, format_func=label_for, key=f"{query_key}_pick")


def _provider_flags(bouncer: Bouncer):
    fp, hp = bouncer.flight_provider, bouncer.hotel_provider
    used = bool(getattr(fp, "used_fallback", False) or getattr(hp, "used_fallback", False))
    errors = list(getattr(fp, "last_errors", []) or [])
    if getattr(hp, "last_error", None):
        errors.append(getattr(hp, "last_error"))
    return used, errors


def _render_advice_list(items: List[AdviceItem], empty: str) -> None:
    if not items:
        st.markdown(f'<div class="bx-empty">{empty}</div>', unsafe_allow_html=True)
        return
    for i, a in enumerate(items, 1):
        r = a.result
        o = r.option
        with st.container(border=True):
            badge = a.label
            beat = " · ✅ Better than cash" if r.is_better_than_cash else ""
            st.markdown(f"**{i}. {o.description}**{beat}  \n<span class='bx-badge bx-fair'>{badge}</span>",
                        unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Effective cost", money(r.effective_cost))
            c2.metric("Method", method_label(r.payment_method))
            if r.cents_per_point:
                c3.metric("¢/point", f"{r.cents_per_point:.2f}")
            st.write(a.advice)
            if r.reasoning and r.reasoning != a.advice:
                st.caption(r.reasoning)
            if o.booking_url:
                st.markdown(f"[Booking path →]({o.booking_url})")


# ----- session init (per-visitor balances; never share balances.json) -----
if "tracker" not in st.session_state:
    st.session_state.tracker = BalanceTracker(persist=False)
    st.session_state.demo_balances = False
if "live_code_entered" not in st.session_state:
    st.session_state.live_code_entered = ""
if "live_searches_used" not in st.session_state:
    st.session_state.live_searches_used = 0
if "force_demo" not in st.session_state:
    st.session_state.force_demo = True  # public default: sample data

# Build providers: demo unless unlocked live and under cap
_use_live, _live_msg = can_run_live(
    st.session_state.live_code_entered, st.session_state.live_searches_used
)
# Still honor BOUNCER_USE_MOCK=1 as hard force
if os.environ.get("BOUNCER_USE_MOCK", "").strip() in ("1", "true", "yes", "on"):
    _use_live = False
    _source_forced = "Mock data (forced)"
else:
    _source_forced = None

_flights, _hotels, _env_source = build_providers_from_env(force_mock=not _use_live)
st.session_state.bouncer = Bouncer(
    flight_provider=_flights, hotel_provider=_hotels, tracker=st.session_state.tracker
)
bouncer: Bouncer = st.session_state.bouncer
_demo_mode = not _use_live

# Hero
st.markdown(
    f"""
<div class="bx-hero">
  <img src="{_svg_data_uri('assets/bouncer-lockup-horizontal-dark.svg')}" alt="Bouncer">
  <div>
    <h1>Only real deals get in<span class="bx-accent">.</span></h1>
    <p>Bouncer checks every way to pay for your trip (cash, points, transfers, bought points)
    and ranks them by real cost. If an award doesn't beat cash, it doesn't get past Bouncer.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

if _demo_mode:
    st.warning("**Demo — sample prices.** Live award search is invite-only while we keep API quotas healthy. "
               "Join the waitlist for early access.")
    with st.expander("Have an access code?"):
        code = st.text_input("Access code", type="password", key="access_code_box")
        if st.button("Unlock live search"):
            if live_unlocked(code):
                st.session_state.live_code_entered = code.strip()
                st.session_state.force_demo = False
                st.success(f"Live search unlocked ({live_cap()} searches this session).")
                st.rerun()
            elif not live_code():
                st.error("Live search isn't enabled on this deployment yet.")
            else:
                st.error("That code doesn't match.")
else:
    left = live_cap() - st.session_state.live_searches_used
    st.info(f"Live search on · {left} search(es) left this session.")

_src_label = _source_forced or ("Demo — sample prices" if _demo_mode else _env_source)
st.caption(f"Data source: **{_src_label}**")

st.markdown("#### Get early access")
_waitlist_form("hero")

st.markdown("#### How Bouncer works")
st.markdown(
    """
<div class="bx-grid">
  <div class="bx-step"><div class="bx-num">1</div><h5 style="margin:0 0 4px">Find a trip</h5>
    <p>Tell Bouncer where and when. It pulls cash fares and award space for the route.</p></div>
  <div class="bx-step"><div class="bx-num">2</div><h5 style="margin:0 0 4px">Compare cash vs points</h5>
    <p>Cash, points, transfers, bought points: ranked by real cost. If an award doesn't beat cash, it doesn't get in.</p></div>
  <div class="bx-step"><div class="bx-num">3</div><h5 style="margin:0 0 4px">Book smart</h5>
    <p>Get the exact steps: which points to transfer, where, and what it saves vs cash.</p></div>
</div>
""",
    unsafe_allow_html=True,
)

# Sidebar balances
with st.sidebar:
    st.header("Your Points & Miles")
    _render_balances(bouncer, "sidebar")

tab_plan, tab_buy, tab_deals = st.tabs(["Plan a trip", "Where to buy points", "Transfer bonuses & hotels"])

with tab_plan:
    st.subheader("Plan a trip")
    st.caption("Tell Bouncer where you're going. It does the points math and shows the exact steps.")

    with st.expander("Your points", expanded=not bool(bouncer.tracker.get_all())):
        _render_balances(bouncer, "plan")

    origin = _airport_picker(
        "Origin", "origin_q", "JFK",
        "Type a city, airport name or code. Top match is selected first (JFK for New York, etc.).",
    )
    destination = _airport_picker(
        "Destination", "dest_q", "LHR",
        "Type a city, airport name or code.",
    )
    c1, c2 = st.columns(2)
    with c1:
        depart = st.date_input("Depart", value=date.today() + timedelta(days=45))
    with c2:
        return_date = st.date_input("Return", value=date.today() + timedelta(days=52))

    col3, col4, col5 = st.columns(3)
    with col3:
        travelers = st.number_input("Travelers", min_value=1, max_value=9, value=1)
    with col4:
        cabin_key = st.selectbox(
            "Cabin",
            options=["economy", "premium_economy", "business", "first"],
            format_func=cabin_label,
            index=0,
        )
    with col5:
        flexible = st.slider("Flexible days ±", 0, 7, 0)

    run = st.button("Find best deals", type="primary", use_container_width=True)
    if run:
        if return_date < depart:
            st.error("Return date can't be before the depart date.")
        else:
            # Live search accounting
            if _use_live:
                st.session_state.live_searches_used += 1

            request = TripRequest(
                origin=origin.strip().upper(),
                destination=destination.strip().upper(),
                depart_date=depart,
                return_date=return_date,
                flexible_days=flexible,
                travelers=int(travelers),
                cabin=CabinClass(cabin_key),
            )
            with st.spinner("Bouncer is comparing cash, points, transfers, and promos..."):
                options = []
                options.extend(
                    bouncer.flight_provider.search(
                        origin=request.origin,
                        destination=request.destination,
                        depart=request.depart_date,
                        return_date=request.return_date,
                        travelers=request.travelers,
                        cabin=request.cabin,
                    )
                )
                if request.return_date:
                    options.extend(
                        bouncer.hotel_provider.search(
                            destination=request.destination,
                            check_in=request.depart_date,
                            check_out=request.return_date,
                            travelers=request.travelers,
                        )
                    )
                items = rank_with_advice(options, bouncer.tracker)
                st.session_state.last_items = items
                st.session_state.last_request = request

            used_fb, errs = _provider_flags(bouncer)
            if _demo_mode or used_fb or "Mock" in _src_label:
                why = "quota reached or provider error" if (used_fb or errs) else "demo mode"
                st.warning(
                    f"Live prices unavailable ({why}), showing sample data. "
                    + (f"Details: {errs[0]}" if errs else "")
                )

    items = st.session_state.get("last_items")
    if items is not None:
        st.markdown(
            f'<div class="bx-step"><div class="bx-num">★</div>'
            f'<h5 style="margin:0 0 4px">Best pick</h5><p>{best_summary(items)}</p></div>',
            unsafe_allow_html=True,
        )
        flights, hotels = split_flights_hotels(items)
        rf, rh = st.tabs(["Flights", "Hotels"])
        with rf:
            _render_advice_list(flights, "No flight options for this search.")
        with rh:
            _render_advice_list(hotels, "No hotel options for these dates.")
        st.caption(savings_note())
        st.markdown("#### Want live prices on your routes?")
        _waitlist_form("after_results")
        with st.expander("Smarter alternatives"):
            st.write("• Consider flexible dates (±3 days) for better award space.")
            st.write("• Nearby airports or positioning flights can unlock cheaper awards.")
            st.write("• Split stays or different hotels if points balances are uneven.")
    else:
        st.markdown(
            '<div class="bx-empty"><b>No search yet.</b><br>Pick a route and dates, then hit '
            '<b>Find best deals</b>. Bouncer will rank cash, points and transfers by real cost — '
            "and tell you exactly what to transfer.</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Deals data
# ---------------------------------------------------------------------------
from bouncer.deals import (  # noqa: E402
    FAIR_MAX_RATIO,
    GOOD_MAX_RATIO,
    days_left,
    load_deals,
    load_meta,
    where_to_buy,
)
from bouncer.valuations import PROGRAM_VALUES  # noqa: E402

_today = date.today()
_deals = load_deals(_today)
_meta = load_meta()
_DASH = "—"


def _dash(v):
    return v if v not in (None, "") else _DASH


def _cpp(v):
    return f"{v:.2f}¢" if isinstance(v, (int, float)) else _DASH


def _cards(items):
    import html as _h

    out = []
    for it in items:
        parts = [f"<h5>{_h.escape(it['title'])}</h5>"]
        if it.get("big"):
            parts.append(f"<div class='bx-big'>{_h.escape(it['big'])}</div>")
        for ln in it.get("lines", []):
            if ln:
                parts.append(f"<p>{_h.escape(ln)}</p>")
        if it.get("link"):
            parts.append(
                f"<p><a href='{_h.escape(it['link'])}' target='_blank' rel='noopener'>"
                f"{_h.escape(it.get('link_text', 'Source'))} →</a></p>"
            )
        out.append("<div class='bx-card'>" + "".join(parts) + "</div>")
    st.markdown("<div class='bx-grid'>" + "".join(out) + "</div>", unsafe_allow_html=True)


with tab_buy:
    st.subheader("Where to buy points")
    st.caption(
        "Points sales, checked at the door. Each sale price is compared with Bouncer's own valuation of the "
        f"program. Deals as of {_deals['as_of']}; verify on the site before you buy."
    )
    st.markdown(
        f'<span class="bx-badge bx-good">Good buy</span> price ≤ {GOOD_MAX_RATIO:.0%} of value &nbsp; '
        f'<span class="bx-badge bx-fair">Fair</span> ≤ {FAIR_MAX_RATIO:.0%} &nbsp; '
        '<span class="bx-badge bx-skip">Skip</span> above 100% &nbsp; '
        '<span class="bx-badge bx-unknown">No verdict</span> price or valuation unknown',
        unsafe_allow_html=True,
    )
    st.info(
        "Buying points only makes sense for a specific redemption you've already found. "
        "Bouncer is advice-only and never sells points.",
        icon="🛎️",
    )
    for r in where_to_buy(_deals["buy_points_sales"], PROGRAM_VALUES, _today):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3.2, 1.3, 1.3, 1.5, 1.7], vertical_alignment="center")
            ratio = f" · {r['ratio']:.0%} of value" if r["ratio"] is not None else ""
            c1.markdown(
                f"**{r['program']}** &nbsp;<span class='bx-badge bx-{r['verdict_level']}'>{r['verdict']}</span>"
                f"<br><span>{r['bonus_or_discount']}</span>"
                f"<br><span class='bx-muted'>{_dash(r.get('note'))}</span>",
                unsafe_allow_html=True,
            )
            c2.metric("Sale price", _cpp(r["cents_per_point"]), help="Cents per point during the sale")
            c3.metric("Bouncer value", _cpp(r["value_cpp"]), help="From Bouncer's valuations (read-only)")
            ends = r["ends"] or r.get("ends_text") or "Ongoing"
            dl = r["days_left"]
            c4.markdown(
                f"<span class='bx-muted'>Ends</span><br>**{ends}**"
                + (
                    f"<br><span class='bx-muted'>{dl} day{'s' if dl != 1 else ''} left{ratio}</span>"
                    if dl is not None
                    else f"<br><span class='bx-muted'>{ratio.strip(' ·') or _DASH}</span>"
                ),
                unsafe_allow_html=True,
            )
            if r.get("link"):
                if r["link_is_official"]:
                    c5.link_button("Buy on official site", r["link"], width="stretch", type="primary")
                else:
                    c5.link_button("See deal source", r["link"], width="stretch")
            c5.caption(
                f"Standard: {_dash(r.get('standard_cpp'))} ¢/pt · Limit: "
                f"{'See site' if not r.get('max_purchase') else r['max_purchase']}"
            )
    st.caption(savings_note())
    st.markdown("#### No sale right now")
    _cards([
        {
            "title": n["program"],
            "lines": [f"Standard: {_cpp(n.get('standard_cpp'))}/pt" if n.get("standard_cpp") else "", n.get("note")],
            "link": n.get("buy_url") or n["source_url"],
            "link_text": "Buy on official site" if n.get("buy_url") else "Source",
        }
        for n in _deals["buy_points_no_sale"]
    ])
    if _meta.get("bank_points_note"):
        st.caption(_meta["bank_points_note"])

with tab_deals:
    st.subheader("Transfer bonuses & hotels")
    st.caption(
        f"Deals as of {_deals['as_of']}. Deals change often and can end early; "
        "verify on the source before transferring."
    )
    st.markdown("#### Transfer bonuses")
    if _deals["transfer_bonuses"]:
        _cards([
            {
                "title": f"{t['bank']} → {t['partner']}",
                "big": f"+{t['bonus_pct']:g}%",
                "lines": [f"Ends {t['ends']} · {days_left(t['ends'], _today)} days left"],
                "link": t["source_url"],
            }
            for t in _deals["transfer_bonuses"]
        ])
    else:
        st.markdown(
            '<div class="bx-empty">No active transfer bonuses right now. Check back soon.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### Transfer partners")
    st.caption("Card → airline/hotel ratios from the Nov 2026 matrix. Active bonuses included when still open.")
    for note in CAVEATS:
        st.caption(f"Note: {note}")
    # Compact sample: group by card
    from collections import defaultdict

    by_card = defaultdict(list)
    for t in load_partners():
        by_card[t.card_program].append(t)
    for card, rows in by_card.items():
        with st.expander(f"{card} ({len(rows)} partners)"):
            for t in rows:
                bonus = ""
                if t.bonus_pct and (not t.bonus_end or t.bonus_end >= _today):
                    bonus = f" · **+{t.bonus_pct:g}%** through {t.bonus_end or '?'}"
                st.write(f"**{t.partner}** · {t.ratio_label}{bonus}")

    st.markdown("#### Trending hotels")
    _cards([
        {
            "title": h["name"],
            "big": _dash(h.get("points_or_price")) if h.get("points_or_price") else "",
            "lines": [f"{_dash(h.get('location'))} · {h['program']}", _dash(h.get("date")), h["why"]],
            "link": h["source_url"],
        }
        for h in _deals["trending_hotels"]
    ])
    st.markdown("#### Hotel points promos")
    _cards([
        {
            "title": h["name"],
            "lines": [h["program"], h["why"], f"Dates: {_dash(h.get('date'))}"],
            "link": h["source_url"],
        }
        for h in _deals["hotel_promos"]
    ])
    st.caption(savings_note())

st.markdown("### FAQ")
with st.expander("What is Bouncer?"):
    st.write(
        "Your travel deal bouncer. Bouncer compares cash, awards, transfer bonuses and points sales, "
        "ranks every way to pay by real cost, and shows the exact steps to book."
    )
with st.expander("Does Bouncer sell points or take bookings?"):
    st.write(
        "No. Bouncer is advice-only. It never sells points and never books for you; "
        "every buy or transfer happens on the program's own site."
    )
with st.expander("Where do the deals come from?"):
    st.write(
        "Public sources such as Upgraded Points, AwardWallet, NerdWallet, The Points Guy and the programs' own "
        "pages. Each deal links to its source. Verdicts use Bouncer's own valuations."
    )
with st.expander("How often are deals updated?"):
    st.write(
        f"Deals are refreshed in batches (current batch: {_deals['as_of']}). Expired deals drop off "
        "automatically, but programs can change or end offers early, so always verify before you buy or transfer."
    )

st.markdown("### Legal")
for _name, _f in LEGAL_PAGES.items():
    with st.expander(_name):
        st.markdown(load_page(_f))

st.markdown(
    '<div class="bx-footer"><span><b>Bouncer</b> · Only real deals get in. Advice only; never sells points. '
    "See Legal above: Privacy · Terms · Disclaimer · Affiliate disclosure.</span>"
    "<span>@bouncertravel</span></div>",
    unsafe_allow_html=True,
)
