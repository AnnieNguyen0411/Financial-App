"""
Refresh every live (non-WRDS) data source and cache it in data/cache/ so the demo runs offline.

    python scripts/refresh_data.py            # everything
    python scripts/refresh_data.py prices     # just ETF prices
    python scripts/refresh_data.py news       # pre-cache headlines for the demo personas

Sources:
  prices -> Yahoo Finance adjusted closes (yfinance), 15 years, ~39 ETFs
  bls    -> BLS Public Data API, OEWS metro wages & employment for the app's occupations
            (optional: set BLS_API_KEY for bigger batches; register free at https://data.bls.gov/registrationEngine/)
  fred   -> FRED / Realtor.com median listing price by metro (MEDLISPRI{cbsa})
  news   -> Google News RSS for each field, city and market query used in the app
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athena import data as D


def news():
    qs = {f["news"] for f in D.careers()["fields"].values()} | {f["news"] + " academia faculty" for f in D.careers()["fields"].values()}
    qs |= {f"{m['name'].split(',')[0]} economy jobs housing" for m in D.ref("metros")["metros"]}
    qs |= {"stock market today", 'graduate students stipend OR "student loans" OR "research funding"'}
    qs |= {f"stock market today {D.ETFS[t]['name']} stocks" for t in ["XLK", "XLV", "SOXX", "IBB", "QQQ"]}
    ok = 0
    for q in sorted(qs):
        items, status = D.get_news(q, force=True)
        ok += bool(items)
        print(f"  {len(items):2d} headlines  {q}  ({status})")
    print(f"news: {ok}/{len(qs)} queries cached")


def main(which):
    if which in ("all", "prices"):
        print("prices:", D.refresh_etf_prices()[1])
    if which in ("all", "bls"):
        print("bls:", D.refresh_oews_metro()[1])
    if which in ("all", "fred"):
        print("fred:", D.refresh_fred_housing()[1])
    if which in ("all", "news"):
        news()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
