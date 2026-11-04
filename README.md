# Bouncer

**Bouncer** is a travel-deal agent that finds the best way to book flights, hotels, and other travel by comparing cash, points/miles, transfers between programs, and buying points on promo.

## Architecture (v0.1)

### Major components
- **Agent** (`bouncer/agent.py`): Orchestrates trip requests, asks clarifying questions, surfaces alternatives.
- **Valuation Engine** (`bouncer/engine.py`): Core math – cash vs direct points vs transfer (with bonuses) vs buying points. Calculates effective USD cost and cents-per-point.
- **Balance Tracker** (`bouncer/tracker.py`): Tracks user’s point/mile balances (file-backed for now).
- **Providers** (`bouncer/providers.py`): Abstract interfaces + mock implementations for flights and hotels.
- **Valuations** (`bouncer/valuations.py`): Static cents-per-point values and transfer partner maps (sourced from TPG/NerdWallet-style data as of late 2026).
- **Models** (`bouncer/models.py`): Data classes for requests, options, results.

### Data sources & APIs (to go live)
| Component              | Real integration options                          | Notes / limits |
|------------------------|---------------------------------------------------|----------------|
| Cash flight fares      | Amadeus, Duffel, FlightPowers (Google Flights), SerpApi | Public or partner access required |
| Award availability     | AwardTool, Seats.aero, Award Travel Finder, AwardSecrets | Many programs have no public API; scraping fragile; login often required |
| Hotel rates            | Booking.com Demand API, Expedia Rapid, hotel loyalty portals | Partner contracts common |
| Loyalty valuations     | TPG monthly, NerdWallet, Frequent Miler           | Static or scrape; update periodically |
| Transfer bonuses       | thePointsPage, MaxPoints, issuer sites            | Short-lived; needs monitoring |
| User balances          | Manual entry or (future) bank/loyalty account linking | No standard API |

**Workarounds for limited data**:
- Use mock providers behind clean interfaces.
- User can paste award search results or balances.
- Cache known award charts and partner availability.
- Partner with specialist award-search APIs for production.

### Deal-valuation engine logic
1. Always compute cash price.
2. For award options: value points at program’s cents-per-point + taxes/fees.
3. Check user’s direct balance; compute gap.
4. For transferable currencies: apply base ratio + any active transfer bonus, value the source points, compare.
5. Optionally consider buying points at current promo rate if cheaper than cash.
6. A deal only counts if effective cost < cash alternative.
7. Rank by lowest effective cost; explain the exact booking path.

## Interactive UI

```bash
cd bouncer
pip install -r requirements.txt
streamlit run app.py
```

Opens a local web app where you can manage balances and plan trips.

CLI:
```bash
PYTHONPATH=. python main.py --origin JFK --destination LHR --depart 2026-12-15 --return-date 2026-12-22
```

Tests:
```bash
PYTHONPATH=. pytest tests/ -q
```

## Configuration
API keys (when you wire real providers) go in environment variables or a `.env` file. See `config.example`.

## Integrations needed to go live
1. Flight cash search API (e.g. Duffel or FlightPowers).
2. Award search API (AwardTool or Seats.aero).
3. Hotel cash + award API.
4. Periodic job to refresh transfer bonuses and valuations.
5. Persistent user store (Postgres) + auth.
6. Alerting (email/push) for price drops and award space matching saved trips.

## Roadmap (prioritized)
1. **Real data providers** – swap mocks for live cash + award APIs.
2. **Persistent multi-user store** + authentication.
3. **Flexible date / nearby airport search** and positioning flight suggestions.
4. **Alert engine** – watch saved trips for award space, transfer bonuses, price drops.
5. **Natural language agent** – conversational interface that asks clarifying questions.
6. **More travel types** – cars, tours, activities with points options.
7. **Optimization** – multi-leg, stopovers, split stays, family pooling.
8. **Mobile / web UI** and booking deep links / affiliate links.
9. **ML ranking** – learn which redemptions users prefer.
10. **Compliance & legal** – terms for points transfers, affiliate disclosures.

---
Built as a clean, modular foundation so the valuation core can stay solid while data sources are swapped in.

## Deploy to Railway

1. In Railway, create a new project from this GitHub repo. `railway.json` / `Procfile` set the start command automatically.
2. Add your keys under the service's **Variables** tab (never commit `.env`): `RAPIDAPI_KEY`, `AWARDTRAVELFINDER_API_KEY` (optional `AWARDTRAVELFINDER_REGISTRATION_KEY`). Without keys, Bouncer runs on mock data.
3. Under **Settings → Networking**, click **Generate Domain** to get a public URL.
