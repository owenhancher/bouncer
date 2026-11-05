"""Bouncer – interactive travel deal agent (Streamlit UI).

Run with: streamlit run app.py
"""

import streamlit as st
from datetime import date, timedelta
from typing import Optional

from bouncer.agent import Bouncer
from bouncer.legal import PAGES as LEGAL_PAGES, load_page, savings_note
from bouncer.airports import label_for, picker_options
from bouncer.live_providers import build_providers_from_env
from bouncer.models import TripRequest, CabinClass, TravelType

# Page config
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
  [data-testid="stToolbar"] {{ display: none; }}
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
    from pathlib import Path

    return "data:image/svg+xml;base64," + base64.b64encode(Path(path).read_bytes()).decode()


# Hero (dark section -> dark-background lockup)
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

# Initialize session state
if "bouncer" not in st.session_state:
    _flights, _hotels, _source = build_providers_from_env()
    st.session_state.bouncer = Bouncer(flight_provider=_flights, hotel_provider=_hotels)
    st.session_state.data_source = _source
if "balances_loaded" not in st.session_state:
    # Seed demo balances on first load
    b = st.session_state.bouncer
    b.update_balance("Chase Ultimate Rewards", 85000, transferable=True)
    b.update_balance("Amex Membership Rewards", 60000, transferable=True)
    b.update_balance("United MileagePlus", 12000)
    b.update_balance("World of Hyatt", 8000)
    b.update_balance("Marriott Bonvoy", 25000)
    st.session_state.balances_loaded = True

bouncer: Bouncer = st.session_state.bouncer
st.caption(f"Data source: **{st.session_state.get('data_source', 'Mock data')}**")


# How Bouncer works
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

# Sidebar – balances
with st.sidebar:
    st.header("Your Points & Miles")
    balances = bouncer.tracker.get_all()
    if balances:
        for bal in balances:
            exp = f" (expires {bal.expires_on})" if bal.expires_on else ""
            kind = "transferable" if bal.transferable else "loyalty"
            st.write(f"**{bal.program}**")
            st.caption(f"{bal.balance:,} · {kind}{exp}")
    else:
        st.info("No balances yet. Add some below.")

    st.divider()
    st.subheader("Add / Update Balance")
    with st.form("balance_form"):
        prog = st.text_input("Program", placeholder="Chase Ultimate Rewards")
        amt = st.number_input("Balance", min_value=0, value=10000, step=1000)
        transferable = st.checkbox("Transferable credit-card points", value=True)
        submitted = st.form_submit_button("Save")
        if submitted and prog:
            bouncer.update_balance(prog, int(amt), transferable=transferable)
            st.success(f"Saved {prog}: {amt:,}")
            st.rerun()

tab_plan, tab_buy, tab_deals = st.tabs(["Plan a trip", "Where to buy points", "Transfer bonuses & hotels"])

with tab_plan:
    # Main form
    st.subheader("Plan a trip")
    st.caption("Tell Bouncer where you're going. It does the points math and shows the exact steps.")
    col1, col2 = st.columns(2)
    with col1:
        _codes = picker_options()
        origin = st.selectbox(
            "Origin",
            options=_codes,
            index=_codes.index("JFK"),
            format_func=label_for,
            help="Type a city, airport name or code, then pick an airport.",
        )
        _dest_codes = [""] + _codes
        destination = st.selectbox(
            "Destination",
            options=_dest_codes,
            index=_dest_codes.index("LHR"),
            format_func=lambda c: label_for(c) if c else "Anywhere (Bouncer suggests)",
            help="Type a city, airport name or code. Choose 'Anywhere' for open-ended ideas.",
        )
    with col2:
        depart = st.date_input("Depart", value=date.today() + timedelta(days=45))
        return_date = st.date_input("Return", value=date.today() + timedelta(days=52))

    col3, col4, col5 = st.columns(3)
    with col3:
        travelers = st.number_input("Travelers", min_value=1, max_value=9, value=1)
    with col4:
        cabin = st.selectbox("Cabin", options=["economy", "premium_economy", "business", "first"], index=0)
    with col5:
        flexible = st.slider("Flexible days ±", 0, 7, 0)

    if st.button("Find best deals", type="primary", use_container_width=True):
        dest = destination.strip() or None
        request = TripRequest(
            origin=origin.strip().upper(),
            destination=dest.upper() if dest else None,
            depart_date=depart,
            return_date=return_date,
            flexible_days=flexible,
            travelers=travelers,
            cabin=CabinClass(cabin),
        )

        with st.spinner("Bouncer is comparing cash, points, transfers, and promos..."):
            rec = bouncer.plan_trip(request)

        st.success(rec.summary)

        if rec.clarifying_questions:
            with st.expander("Clarifying questions", expanded=True):
                for q in rec.clarifying_questions:
                    st.write(f"• {q}")

        st.subheader("Ranked recommendations")
        if not rec.ranked_options:
            st.warning("No options found. Try different dates or airports.")
        else:
            for i, r in enumerate(rec.ranked_options, 1):
                with st.container(border=True):
                    badge = "✅ Better than cash" if r.is_better_than_cash else "💵 Cash"
                    st.markdown(f"**{i}. {r.option.description}** · {badge}")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Effective cost", f"${r.effective_cost:,.0f}")
                    c2.metric("Method", r.payment_method.replace("_", " ").title())
                    if r.cents_per_point:
                        c3.metric("¢/point", f"{r.cents_per_point:.2f}")
                    st.write(r.reasoning)
                    if r.gap_to_close:
                        st.info(f"Gap: need **{r.gap_to_close:,}** more points (transfer or buy).")
                    if r.option.booking_url:
                        st.markdown(f"[Booking path →]({r.option.booking_url})")

        if rec.alternatives:
            with st.expander("Smarter alternatives"):
                for a in rec.alternatives:
                    st.write(f"• {a}")
        st.caption(savings_note())
    else:
        st.markdown(
            '<div class="bx-empty"><b>No search yet.</b><br>Pick a route and dates, then hit '
            '<b>Find best deals</b>. Bouncer will rank cash, points, transfers and bought points by real cost.</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Deals data (advice-only reference data from bouncer/deals.json)
# ---------------------------------------------------------------------------
from datetime import date as _date  # noqa: E402

from bouncer.deals import (  # noqa: E402
    FAIR_MAX_RATIO,
    GOOD_MAX_RATIO,
    days_left,
    load_deals,
    load_meta,
    where_to_buy,
)
from bouncer.valuations import PROGRAM_VALUES  # noqa: E402

_today = _date.today()
_deals = load_deals(_today)
_meta = load_meta()
_DASH = "—"


def _dash(v):
    return v if v not in (None, "") else _DASH


def _cpp(v):
    return f"{v:.2f}¢" if isinstance(v, (int, float)) else _DASH


def _cards(items):
    """Render a responsive grid of cards. items: dicts with title, big, lines, link, link_text."""
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
            parts.append(f"<p><a href='{_h.escape(it['link'])}' target='_blank' rel='noopener'>"
                         f"{_h.escape(it.get('link_text', 'Source'))} →</a></p>")
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
                + (f"<br><span class='bx-muted'>{dl} day{'s' if dl != 1 else ''} left{ratio}</span>"
                   if dl is not None else f"<br><span class='bx-muted'>{ratio.strip(' ·') or _DASH}</span>"),
                unsafe_allow_html=True,
            )
            if r["link_is_official"]:
                c5.link_button("Buy on official site", r["link"], width="stretch", type="primary")
            else:
                c5.link_button("See deal source", r["link"], width="stretch")
            c5.caption(
                f"Standard: {_dash(r.get('standard_cpp'))} ¢/pt · Limit: "
                f"{'See site' if not r.get('max_purchase') else r['max_purchase']}"
            )

    st.markdown("#### No sale right now")
    _cards([
        {"title": n["program"],
         "lines": [f"Standard: {_cpp(n.get('standard_cpp'))}/pt" if n.get("standard_cpp") else "", n.get("note")],
         "link": n.get("buy_url") or n["source_url"],
         "link_text": "Buy on official site" if n.get("buy_url") else "Source"}
        for n in _deals["buy_points_no_sale"]
    ])
    st.caption(savings_note())
    if _meta.get("bank_points_note"):
        st.caption(_meta["bank_points_note"])
    st.caption(
        "Sources: [Upgraded Points](https://upgradedpoints.com/news/current-point-purchase-promotions/) · "
        "[AwardWallet](https://awardwallet.com/news/current-promotions-buy-points-miles/) · "
        "[TPG valuations](https://thepointsguy.com/loyalty-programs/monthly-valuations/) (reference only; "
        "verdicts use Bouncer's valuations). 'Standard' prices marked (derived) are back-calculated from the sale."
    )

with tab_deals:
    st.subheader("Transfer bonuses & hotels")
    st.caption(
        f"Deals as of {_deals['as_of']}. Deals change often and can end early; "
        "verify on the source before transferring."
    )
    st.markdown("#### Transfer bonuses")
    if _deals["transfer_bonuses"]:
        _cards([
            {"title": f"{t['bank']} → {t['partner']}", "big": f"+{t['bonus_pct']:g}%",
             "lines": [f"Ends {t['ends']} · {days_left(t['ends'], _today)} days left"],
             "link": t["source_url"]}
            for t in _deals["transfer_bonuses"]
        ])
    else:
        st.markdown('<div class="bx-empty">No active transfer bonuses right now. Check back soon.</div>',
                    unsafe_allow_html=True)

    st.markdown("#### Trending hotels")
    _cards([
        {"title": h["name"], "big": _dash(h.get("points_or_price")) if h.get("points_or_price") else "",
         "lines": [f"{_dash(h.get('location'))} · {h['program']}", _dash(h.get("date")), h["why"]],
         "link": h["source_url"]}
        for h in _deals["trending_hotels"]
    ])

    st.markdown("#### Hotel points promos")
    _cards([
        {"title": h["name"], "lines": [h["program"], h["why"], f"Dates: {_dash(h.get('date'))}"],
         "link": h["source_url"]}
        for h in _deals["hotel_promos"]
    ])
    st.caption(savings_note())

# Hotels going viral (Video Scout). OFF unless BOUNCER_SHOW_VIDEOS=1; never breaks the page.
try:
    from video_scout.site import render as _render_viral_videos

    _render_viral_videos(st)
except Exception:
    pass

# FAQ
st.markdown("### FAQ")
with st.expander("What is Bouncer?"):
    st.write("Your travel deal bouncer. Bouncer compares cash, awards, transfer bonuses and points sales, "
             "ranks every way to pay by real cost, and shows the exact steps to book.")
with st.expander("Does Bouncer sell points or take bookings?"):
    st.write("No. Bouncer is advice-only. It never sells points and never books for you; "
             "every buy or transfer happens on the program's own site.")
with st.expander("Where do the deals come from?"):
    st.write("Public sources such as Upgraded Points, AwardWallet, NerdWallet, The Points Guy and the programs' own "
             "pages. Each deal links to its source. Verdicts use Bouncer's own valuations.")
with st.expander("How often are deals updated?"):
    st.write(f"Deals are refreshed in batches (current batch: {_deals['as_of']}). Expired deals drop off "
             "automatically, but programs can change or end offers early, so always verify before you buy or transfer.")

st.markdown("### Legal")
for _name, _f in LEGAL_PAGES.items():
    with st.expander(_name):
        st.markdown(load_page(_f))

st.markdown(
    '<div class="bx-footer"><span><b>Bouncer</b> · Only real deals get in. Advice only; never sells points. See Legal above: Privacy · Terms · Disclaimer · Affiliate disclosure.</span>'
    '<span>@bouncertravel</span></div>',
    unsafe_allow_html=True,
)
