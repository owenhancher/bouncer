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
    page_title="Bouncer",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("✈️ Bouncer")
st.caption("Travel deal agent on steroids — cash vs points, transfers, and promotions.")

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

# Main form
st.header("Plan a trip")
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

st.divider()
st.caption("Bouncer v0.1 · Mock data behind swappable providers. Wire real award/cash APIs to go live.")
