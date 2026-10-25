# Home Decision Studio

**Live page:** https://pinedakevin.github.io/Claude_Projects/home-decision-studio/

An interactive guide to choosing where to buy a 3–4 bedroom house in Salt Lake County and north Utah County, and whether to buy at all. It covers 20 cities and works for anyone: first-time buyers, veterans, and FHA borrowers.

Set your loan (conventional, FHA or VA, 30 or 15 years), down payment, monthly limit, where you work, how long you'll stay, and what matters to you. The page then:

- ranks all 20 cities for you, using cost, own vs rent, safety, schools, drive time and value trend
- shows the full monthly payment for a typical home: principal and interest, county tax, insurance, PMI or FHA mortgage insurance, and HOA
- compares your net worth after N years of owning against renting and investing the difference
- puts up to three cities side by side

## Data

| What | Source | Updated |
|---|---|---|
| Home values | [Zillow Home Value Index](https://www.zillow.com/research/data/): 3-bed, 4-bed and single-family, middle tier | Weekly, automatically |
| Conventional rates | [Freddie Mac PMMS](https://www.freddiemac.com/pmms) via [FRED](https://fred.stlouisfed.org/series/MORTGAGE30US) | Weekly, automatically |
| VA and FHA rates | Conventional rate plus the gap measured from real quotes in Oct 2026 | Weekly, automatically |
| Rents | Median of 466 live 3–4 bed house listings (Oct 2026) | By hand |
| Crime, schools, census, drive times | NeighborhoodScout and FBI, USBE, Niche, GreatSchools, Census QuickFacts/ACS, OpenStreetMap routing | By hand |

The weekly refresh runs from [`.github/workflows/refresh-home-decision-studio.yml`](../.github/workflows/refresh-home-decision-studio.yml) on Fridays and commits only when a number changes. To run it now: **Actions → Refresh Home Decision Studio data → Run workflow**. To run it on your own machine:

```
pip install requests
python home-decision-studio/scripts/refresh_data.py
```

If a source can't be reached, the old numbers stay in place.

## Files

- `index.html`: the page (plain HTML and JavaScript, using [d3](https://d3js.org) v7.9.0, included in `vendor/`)
- `data/*.csv`: every number the page uses; edit them directly to update rents, crime or schools
- `data/meta.json`: when the data was last refreshed, and from where
- `scripts/refresh_data.py`: the automatic refresh

Neighborhoods vary a lot within a city. Use this to narrow the list, then go tour streets.
