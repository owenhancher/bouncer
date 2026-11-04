"""Bouncer – interactive travel deal agent (Streamlit UI).

Run with: streamlit run app.py
"""

import streamlit as st
from datetime import date, timedelta
from typing import Optional

from bouncer.agent import Bouncer
from bouncer.live_providers import build_providers_from_env
from bouncer.models import TripRequest, CabinClass, TravelType

# Page config
st.set_page_config(
    page_title="Bouncer · Only real deals get in.",
    page_icon="assets/bouncer-favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
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
        origin = st.text_input("Origin", value="JFK", help="Airport code")
        destination = st.text_input("Destination", value="LHR", help="Airport code or city. Leave blank for 'anywhere'")
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
    st.dataframe(
        [
            {"Program": n["program"], "Note": _dash(n.get("note")),
             "Buy page": n.get("buy_url") or n["source_url"]}
            for n in _deals["buy_points_no_sale"]
        ],
        column_config={"Buy page": st.column_config.LinkColumn("Link", display_text="link")},
        hide_index=True,
        width="stretch",
    )
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
    _src = {"Source": st.column_config.LinkColumn("Source", display_text="source")}

    st.markdown("#### Transfer bonuses")
    if _deals["transfer_bonuses"]:
        st.dataframe(
            [
                {"Bank": t["bank"], "Partner": t["partner"], "Bonus": f"+{t['bonus_pct']:g}%",
                 "Ends": t["ends"], "Days left": days_left(t["ends"], _today), "Source": t["source_url"]}
                for t in _deals["transfer_bonuses"]
            ],
            column_config=_src, hide_index=True, width="stretch",
        )
    else:
        st.info("No active transfer bonuses right now.")

    st.markdown("#### Trending hotels")
    st.dataframe(
        [
            {"Hotel": h["name"], "Location": _dash(h.get("location")), "Program": h["program"],
             "Points / price": _dash(h.get("points_or_price")), "Date": _dash(h.get("date")),
             "Why": h["why"], "Source": h["source_url"]}
            for h in _deals["trending_hotels"]
        ],
        column_config=_src, hide_index=True, width="stretch",
    )

    st.markdown("#### Hotel points promos")
    st.dataframe(
        [
            {"Promo": h["name"], "Program": h["program"], "Offer": h["why"],
             "Ends / dates": _dash(h.get("date")), "Source": h["source_url"]}
            for h in _deals["hotel_promos"]
        ],
        column_config=_src, hide_index=True, width="stretch",
    )

st.divider()
st.caption("Bouncer · Only real deals get in. Advice only; Bouncer never sells points.")
