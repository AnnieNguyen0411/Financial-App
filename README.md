# Athena Capital
**Wealth planning for master's and PhD students.** Built in Python Shiny (Core) · runs from `app.py` in Positron.

Graduate students have an unusual financial life: a modest stipend that ends on a date you only roughly know, tax rules nobody explains (fellowships with no withholding, the student FICA exception, nonresident-alien rules), loans that quietly accrue interest, and one huge decision: *which degree and career path, in which city?* Athena Capital takes a student from "here is who I am" to "here is what I should do with my money and what could happen."

**How it flows.** The app opens on a **Welcome to Athena Capital** screen. *Start my plan* launches a 9-step persona builder (about you → degree → funding & income → career goals → assets & debts → monthly spending → goals → risk questionnaire → review). Questions adapt to the client: PhD questions (PhD year and length, postdoc years, tenure-track odds, PhD industry offer, the academia sector) only appear for clients who are in a PhD or postdoc, or plan to start one. Master's students heading to work see master's questions only. *Build my plan* opens the main app, where nine tabs share the persona. A persona bar on every page summarizes the client; **Edit persona** (or any chip in the bar) reopens the builder at the right step, and *Apply changes* updates every module. From the welcome screen you can also open a saved client or jump in with a demo persona.

| Tab | Course module | What it does |
|---|---|---|
| **Overview** | (dashboard) | Health score (0-100), net worth vs. peers, monthly surplus, career-path value, stipend purchasing power; plan timeline; auto-generated priority actions; net-worth outlook. |
| **Life & Career** | **1. Client profile** | Compares the paths that fit the client on earnings, PV and break-even age. Master's students: master's → industry / government / nonprofit, plus an opt-in *Compare with doing a PhD* what-if. PhD students: PhD → industry / government / nonprofit, PhD → postdoc → academia with *your* tenure-track probability, and "mastering out". Peer ranking vs. Fed SCF; stipend purchasing power vs. NSF GRFP after BEA cost-of-living; risk tolerance (questionnaire) vs. risk capacity; human capital and the "don't double up on your own industry" hedge. |
| **Portfolio Studio** | **2. Portfolio** | A toolbar at the top shows the market-data source with an **Update market data** button and the *If you had invested…* horizon picker. Build a portfolio from U.S./developed/emerging stocks, large/mid/small, blend/growth/value, ESG core, 5 bond types, REITs, gold, cash, plus up to three sector/theme tilts (11 GICS sectors, semiconductors, biotech, clean energy, Nasdaq-100, dividends). Simulate "if I had invested" over **1M, 3M, 6M, YTD, 1Y, 3Y, 5Y, 10Y** with a lump sum plus monthly stipend contributions, rebalancing and fees; benchmark, drawdowns, trailing-return table, correlations, Sharpe, CAPM / Fama-French betas; 1,000-path Monte Carlo to retirement. |
| **Life Events** | **3. Life events** | Graduation delayed, funding gap and leaving with a master's (PhD clients only), internship, signing bonus, layoff, OPT/visa gap (international clients only), ongoing job-loss risk, child, medical emergency, windfall, and **replays of real crashes** (2008, 2020, 2022, 2000, 1973) at any age; sequence-of-returns demo. |
| **Budget & Taxes** | **4. Cash flow, tax & goals** | Monthly Sankey; student-specific 2026 taxes (fellowship vs. wages, student FICA exception, F-1/J-1 nonresident rules incl. India treaty, state brackets for 25 states, quarterly estimates); savings waterfall (card debt → cash cushion → Roth IRA → emergency fund → goals → 403(b)/457(b) → brokerage); goals dashboard with "how to close the gap"; loans (2026-27 rates, OBBBA caps, Grad PLUS end); asset location. |
| **Where to Live** | location & housing (extra) | One page: scores 31 metros on cost-adjusted after-tax pay for your field and sector (your own expected salary for master's clients, NSF SED medians for PhD clients), housing burden, field-industry match and cost of living, with adjustable weights; opportunity map; ranking; city detail; one click to make a city your target. The **focus city** then drives *Homes & rentals*: a **neighborhood price map that works with no API key** (every ZIP code within your chosen distance, colored by typical rent for your bedroom count or typical list price, faded when over budget, with a table of in-budget neighborhoods and one-click Zillow / Realtor.com / Redfin searches for each ZIP), optional live listing pins with a free **RentCast** API key, pre-filtered links to Zillow, Realtor.com, Redfin, Trulia, Apartments.com, Zumper; local market stats (Realtor.com Sep 2026, FRED history); rent vs. buy at the current Freddie Mac rate. |
| **News** | briefing (extra) | Google News headlines for your field and career, target city, markets and your holdings, and grad-school money; market snapshot. Cached for offline demos. |
| **Travel & Deals** | toolkit (extra) | Trip planner for conferences/visits home: distance, fly vs. train vs. drive, route map, pre-filled **Google Flights, Kayak, Skyscanner, Amtrak, Wanderu, Rome2Rio, Google Hotels** searches, trip budget with reimbursement; **cash-back optimizer** for your cards and a student-perks directory. |
| **Report & Methods** | report (extra) | Downloadable client report (HTML → print to PDF), data-freshness panel with refresh buttons, every source, every assumption. |

**Design.** A flat finance look: black top bar, deep azure and blue tones throughout (red only for losses), Source Serif 4 for headings and figures, IBM Plex Sans for the interface and tables.

**Data flow:** persona builder → profile → career paths & human capital → recommended stock/bond mix → portfolio → Monte Carlo (contributions come from the Budget module while in school and from the chosen career path after graduation) → life-event scenarios. The target city drives salaries, state taxes, housing goals, news and travel.

**Demo personas** (welcome screen → *Explore a demo client*, or **Clients → Welcome screen** from inside the app): **Mei Chen**, 2nd-year CS PhD at Carnegie Mellon (Pittsburgh) aiming for industry AI research in Seattle; **Arjun Mehta**, self-funded international (F-1, India treaty) 1-year master's in statistics at Columbia heading to Austin; **Sofia Alvarez**, 4th-year biology PhD on a fellowship in Boston on the academic track (quarterly estimated taxes, postdoc, 20% tenure-track odds).

---

## Setup (Positron)
1. Unzip, then **File → Open Folder…** and choose the `athena-capital` folder.
2. In the Terminal:
   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   Select the `.venv` interpreter (bottom-right of Positron).
3. Open `app.py` → **Run App** (or `shiny run --reload app.py`, then open http://127.0.0.1:8000).

The app runs immediately on the bundled data. Before you present, load the live data once so everything is cached locally:

```bash
python scripts/refresh_data.py         # ETF prices (Yahoo Finance), BLS metro wages, FRED housing, news headlines
pip install wrds && python scripts/fetch_wrds_data.py   # WRDS: Fama-French factors + CRSP monthly ETF returns
```
(You can also use **Update market data** at the top of **Portfolio Studio**, and the refresh buttons on **Report & Methods** and **Where to Live**.)

**Optional keys** (never stored in the code):
- **RentCast** (free tier at app.rentcast.io): paste it into *Where to Live → Homes & rentals → RentCast API key*, or set it once before starting the app (`export RENTCAST_API_KEY=...`; Windows PowerShell: `$env:RENTCAST_API_KEY="..."`). It's never written to disk. Listings you fetch are saved to `data/cache/` so they still show during an offline demo. Without a key, the map shows neighborhood prices only.
- **BLS** (free registration): `export BLS_API_KEY=...` before `refresh_data.py` for larger batches.
- **WRDS:** the `wrds` package prompts for your login. Never write your password in a file.

### Demo-day checklist
- Run `scripts/refresh_data.py` and `scripts/fetch_wrds_data.py` the day before; everything lands in `data/cache/`.
- If Wi-Fi is unreliable, set **Map style → Plain (offline)** at the top of **Where to Live** (it also applies to the Travel map). Fonts and icons are bundled in `www/vendor/`, so the app looks the same offline; charts, maps and cached news all work offline.
- **Client files:** the builder saves each persona to `profiles/` (untick *Save this client file* on the review step to skip). Use **Clients** in the persona bar or the welcome screen to open or delete them.
- `docs/screenshots/` has a backup of the welcome screen, the persona builder and every tab, taken in proxy mode before market data was refreshed (the street map tiles were offline when they were taken).

---

## Project structure
```
app.py                      UI + server (welcome screen, persona builder, 9 tabs, client files, report)
athena/data.py              bundled + cached data, live fetchers (yfinance, BLS API, FRED, Google News RSS, RentCast)
athena/careers.py           Module 1: paths, wages by metro, human capital, peers, risk tolerance/capacity
athena/portfolio.py         Module 2: builder, simulator, risk/factor stats, Monte Carlo, crash windows
athena/events.py            Module 3: life events and sequence-of-returns demo
athena/budget.py            Module 4: student taxes, cash flow, waterfall, goals, loans, health score
athena/location.py          metro scoring, rent vs. buy, listing links
athena/travel.py            trip planner, booking links, card optimizer, perks
athena/profiles.py          save / load / delete client profiles (profiles/*.json)
athena/report.py            downloadable report
data/reference/*.json       verified reference tables with sources inside each file
data/bundled/*.csv          public datasets (Shiller S&P 500, CPI, 10y yields, gold, VIX, Case-Shiller, S&P 500 sectors)
data/cache/                 live data pulled on your machine (git-ignore it if you like)
scripts/                    refresh_data.py, fetch_wrds_data.py, build_zip_housing.py (rebuilds the neighborhood price table)
www/styles.css              theme
www/vendor/                 bundled fonts (Source Serif 4, IBM Plex Sans; SIL OFL) and Bootstrap Icons (MIT)
```

## Data sources
- **WRDS:** Fama-French monthly factors (`ff.factors_monthly`) for factor betas and alpha; CRSP monthly total returns for the ETF universe (used by the Portfolio Studio when Yahoo prices aren't cached).
- **Market history (non-WRDS):** Robert Shiller's online data (S&P 500, dividends, CPI, long rates), U.S. CPI, 10-yr Treasury yields, gold, CBOE VIX, S&P/Case-Shiller national index, S&P 500 constituents (all via github.com/datasets, through Sep–Oct 2026).
- **ETF prices:** Yahoo Finance via `yfinance`.
- **Doctorate salaries:** NSF NCSES Survey of Earned Doctorates 2024 (Table 6-7; NSF 26-312).
- **Occupation wages:** BLS OEWS May 2025 national Table 1; metro wages via the BLS Public Data API.
- **Cost of living:** BEA Regional Price Parities 2024 by metro (released Feb 19, 2026, via FRED).
- **Neighborhood housing (ZIP code):** HUD FY2026 Small Area Fair Market Rents (0–4 bedrooms); Zillow Observed Rent Index and Home Value Index by ZIP (Mar 31, 2026); Realtor.com inventory core metrics by ZIP (median list price, active listings, days on market; Mar 2026); ZIP locations from the Census 2024 ZCTA Gazetteer and GeoNames (CC BY 4.0). Bundled in `data/bundled/zip_housing.csv` (3,734 ZIPs within 25 miles of the app's 31 metros); built by `scripts/build_zip_housing.py` from the tidy extracts in github.com/cavandonohoe/cavandonohoe.github.io, whose scripts pull the official files unchanged. Sources and dates are in `data/bundled/zip_housing_sources.json`.
- **Housing:** Realtor.com September 2026 Top-50 Metros report; FRED/Realtor.com median listing price series; Freddie Mac PMMS (30-yr 7.18%, Nov 5, 2026).
- **Taxes & accounts:** IRS Rev. Proc. 2025-32 (2026 brackets, $16,100 standard deduction); IRS Notice 2025-67 ($24,500 403(b)/457(b), $7,500 IRA, Roth phase-out); SSA 2026 wage base; Tax Foundation 2026 state brackets; SECURE Act §106 (stipends count as IRA compensation); IRC §117, §3121(b)(10), §3121(b)(19).
- **Student loans:** FSA GENERAL-26-33 (8.07% grad unsubsidized for 2026-27, 1.057% fee); One Big Beautiful Bill Act (P.L. 119-21): Grad PLUS ends for new borrowers July 1, 2026; $20,500/yr and $100,000 aggregate caps.
- **Peers & benchmarks:** Federal Reserve SCF 2022 net-worth percentiles by age; NSF GRFP $37,000 stipend.
- **News / listings / booking:** Google News RSS; RentCast API; deep links to booking sites (no payments handled in-app).

## Key assumptions & limitations
- PhD-track earnings use national median starting salaries for new PhDs by field and sector (NSF SED); master's-track earnings use the client's own expected salary (government and nonprofit scaled by SED sector pay ratios). Both are scaled by a metro factor (BLS metro wages when refreshed, otherwise BEA price levels). Raises decay over time; academia adds one promotion step. Individual offers vary a lot.
- The academia path is an expected value: your tenure-track probability × faculty pay, plus the rest in industry at a 10% late-switch discount.
- Taxes are simplified: single filer; no local taxes, credits or itemized deductions; nonresident treaty benefits only as the exempt amount you enter.
- Monte Carlo resamples 12-month blocks of 1928–2026 U.S. history in real dollars. Equity shocks are scaled by your portfolio's volatility relative to the S&P 500. Cash is modeled as inflation + 0.5%/yr.
- Before market data is refreshed, the Portfolio Studio runs in proxy mode (each ETF follows its asset class), so sector and size tilts only matter once real prices load.
- Metro "field match" is a qualitative keyword tag of each metro's major industries.
- Neighborhood prices are typical values by ZIP code, not individual listings. HUD Small Area FMRs are 40th-percentile rents and HUD caps some high-rent ZIPs; Zillow indexes are smoothed; Realtor.com figures are monthly medians. Distances are measured from each metro's downtown point.

> **Disclaimer:** Athena Capital is an educational class project and does not provide financial, investment, tax, legal or immigration advice.
