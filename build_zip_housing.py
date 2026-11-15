"""Build data/bundled/zip_housing.csv: neighborhood (ZIP-code) rents, home values and listing activity
around each metro in the app, so the Where to Live map works with no API key.

Inputs (official sources; values are copied unchanged):
  * HUD FY2026 Small Area Fair Market Rents by ZIP, 0-4 bedrooms
    https://www.huduser.gov/portal/datasets/fmr/fmr2026/fy2026_safmrs.xlsx
  * Zillow Observed Rent Index (ZORI, all homes + multifamily, smoothed) and Zillow Home Value Index
    (ZHVI, mid-tier) by ZIP, latest month = Mar 31 2026
    https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv
    https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv
  * Realtor.com Residential Data, Inventory Core Metrics by ZIP, Mar 2026
    https://econdata.s3-us-west-2.amazonaws.com/Reports/Core/RDC_Inventory_Core_Metrics_Zip.csv
  * ZIP coordinates: U.S. Census 2024 ZCTA Gazetteer (internal points) where available, otherwise
    GeoNames postal-code coordinates (CC BY 4.0) via the `zipcodes` Python package.
The first three were taken from the tidy extracts in github.com/cavandonohoe/cavandonohoe.github.io
(data/hud_safmr_zcta.csv, data/us_rental_markets_zip.csv, data/realtor_com_zip.csv; commit 194e6c5),
whose scripts pull the official files above.

Usage: python scripts/build_zip_housing.py <folder with the three CSVs>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from athena import data as D  # noqa: E402

RADIUS_MI = 25.0


def haversine(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


def main(src: Path):
    import zipcodes  # pip install zipcodes (only needed to rebuild this file)

    hud = pd.read_csv(src / "hud_safmr_zcta.csv", dtype={"zip": str})
    zil = pd.read_csv(src / "us_rental_markets_zip.csv", dtype={"zip": str})
    rdc = pd.read_csv(src / "realtor_com_zip.csv", dtype={"zip": str})
    zips = sorted(set(hud.zip) | set(zil.zip) | set(rdc.zip))

    geo = {r.zip: (r.zip_lat, r.zip_lon, r.city, r.state, "Census 2024 ZCTA Gazetteer") for r in zil.itertuples()}
    for z in zips:
        if z in geo:
            continue
        m = zipcodes.matching(z)
        # residential delivery ZIPs only (skip PO-box and single-business ZIPs, which sit on top of post offices)
        if m and m[0].get("zip_code_type") == "STANDARD" and m[0].get("lat") and m[0].get("long"):
            geo[z] = (float(m[0]["lat"]), float(m[0]["long"]), m[0]["city"], m[0]["state"], "GeoNames")

    g = pd.DataFrame([(z, *v) for z, v in geo.items()], columns=["zip", "lat", "lon", "city", "state", "coord_source"])
    metros = D.metros()
    keep = np.zeros(len(g), dtype=bool)
    for r in metros.itertuples():
        keep |= haversine(r.lat, r.lon, g.lat.values, g.lon.values) <= RADIUS_MI
    g = g[keep]

    out = (g.merge(hud.rename(columns={f"safmr_{b}br": f"hud_{b}br" for b in range(5)}), on="zip", how="left")
            .merge(zil[["zip", "zori_latest", "zhvi_latest", "zhvi_yoy_pct"]].rename(columns={"zori_latest": "zori", "zhvi_latest": "zhvi"}),
                   on="zip", how="left")
            .merge(rdc[["zip", "rdc_median_list", "rdc_median_list_yoy", "rdc_active_listings", "rdc_dom", "rdc_price_reduced_share"]],
                   on="zip", how="left"))
    price_cols = ["hud_2br", "zori", "zhvi", "rdc_median_list"]
    out = out[out[price_cols].notna().any(axis=1)].copy()
    # a few Zillow rows have no city name: use the USPS city from the zipcodes package
    missing = out.city.isna()
    out.loc[missing, "city"] = [(zipcodes.matching(z) or [{}])[0].get("city") for z in out.loc[missing, "zip"]]
    out["city"] = out.city.fillna("").str.title()
    out = out.round({"lat": 5, "lon": 5, "zhvi": 0, "zori": 0, "rdc_median_list": 0, "rdc_median_list_yoy": 4,
                     "rdc_price_reduced_share": 4})
    dest = ROOT / "data" / "bundled" / "zip_housing.csv"
    out.sort_values("zip").to_csv(dest, index=False)
    meta = {
        "rows": len(out), "radius_miles": RADIUS_MI,
        "hud": "HUD Small Area Fair Market Rents FY2026 (40th-percentile gross rent, effective Oct 1 2025), "
               "https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html",
        "zillow": "Zillow Research: ZORI (typical rent, all homes + multifamily, smoothed) and ZHVI (typical home value, mid-tier), "
                  "ZIP level, Mar 31 2026, https://www.zillow.com/research/data/",
        "realtor": "Realtor.com Residential Data: inventory core metrics by ZIP (median list price, active listings, days on market, "
                   "share with price cuts), Mar 2026, https://www.realtor.com/research/data/",
        "coords": "U.S. Census Bureau 2024 ZCTA Gazetteer; GeoNames postal codes (CC BY 4.0) via the zipcodes package",
        "assembled_from": "github.com/cavandonohoe/cavandonohoe.github.io data extracts (commit 194e6c5) built from the official files",
        "as_of": {"hud": "FY2026", "zillow": "2026-03-31", "realtor": "2026-03"},
    }
    (ROOT / "data" / "bundled" / "zip_housing_sources.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {dest} ({len(out)} ZIPs; {out.coord_source.value_counts().to_dict()})")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("."))
