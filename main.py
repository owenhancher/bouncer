#!/usr/bin/env python3
"""CLI entrypoint for Bouncer."""

import argparse
from datetime import date, timedelta

from bouncer.agent import Bouncer
from bouncer.live_providers import build_providers_from_env
from bouncer.models import TripRequest, CabinClass


def main():
    parser = argparse.ArgumentParser(description="Bouncer – travel deal agent")
    parser.add_argument("--origin", default="JFK", help="Origin airport code")
    parser.add_argument("--destination", default="LHR", help="Destination (or leave for anywhere)")
    parser.add_argument("--depart", help="YYYY-MM-DD")
    parser.add_argument("--return-date", help="YYYY-MM-DD")
    parser.add_argument("--travelers", type=int, default=1)
    parser.add_argument("--cabin", default="economy", choices=["economy", "business"])
    parser.add_argument("--set-balance", nargs=2, metavar=("PROGRAM", "AMOUNT"), help="Set a balance")
    parser.add_argument("--mock", action="store_true", help="Force mock data (or set BOUNCER_USE_MOCK=1)")
    args = parser.parse_args()

    flights, hotels, source = build_providers_from_env(force_mock=True if args.mock else None)
    bouncer = Bouncer(flight_provider=flights, hotel_provider=hotels)
    print(f"Data source: {source}")

    if args.set_balance:
        prog, amt = args.set_balance
        bouncer.update_balance(prog, int(amt), transferable="Chase" in prog or "Amex" in prog or "Citi" in prog)
        print(f"Set {prog} balance to {amt}")
        return

    depart = date.fromisoformat(args.depart) if args.depart else date.today() + timedelta(days=45)
    ret = date.fromisoformat(args.return_date) if args.return_date else depart + timedelta(days=7)

    request = TripRequest(
        origin=args.origin,
        destination=args.destination,
        depart_date=depart,
        return_date=ret,
        travelers=args.travelers,
        cabin=CabinClass(args.cabin),
    )

    # Seed some demo balances
    bouncer.update_balance("Chase Ultimate Rewards", 85000, transferable=True)
    bouncer.update_balance("United MileagePlus", 12000)
    bouncer.update_balance("World of Hyatt", 8000)

    rec = bouncer.plan_trip(request)

    print("\n=== Bouncer Recommendation ===")
    print(rec.summary)
    if rec.clarifying_questions:
        print("\nClarifying questions:")
        for q in rec.clarifying_questions:
            print(f"  - {q}")
    print("\nRanked options:")
    for i, r in enumerate(rec.ranked_options[:5], 1):
        better = "✓ better than cash" if r.is_better_than_cash else ""
        print(f"{i}. {r.option.description}")
        print(f"   Method: {r.payment_method} | Effective: ${r.effective_cost:.0f} {better}")
        print(f"   {r.reasoning}")
        if r.gap_to_close:
            print(f"   Gap: need {r.gap_to_close:,} more points")
    print("\nAlternatives to consider:")
    for a in rec.alternatives:
        print(f"  - {a}")


if __name__ == "__main__":
    main()
