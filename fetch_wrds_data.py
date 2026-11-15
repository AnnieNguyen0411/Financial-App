"""
Pull WRDS data ONCE and cache it locally; the app never connects to WRDS at runtime.

    pip install wrds
    python scripts/fetch_wrds_data.py

The `wrds` package prompts for your username/password (and can create ~/.pgpass for you).
NEVER put your WRDS password in this file or anywhere in the repository.

Writes:
  data/cache/wrds_ff_factors.csv    Fama-French monthly factors (mktrf, smb, hml, umd, rf)   -> factor betas & alpha in Portfolio Studio
  data/cache/wrds_crsp_monthly.csv  CRSP monthly total returns for the app's ETF universe     -> long-history checks, documented in Methods
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from athena.data import CACHE, ETFS  # noqa: E402

START = "1993-01-01"


def main() -> None:
    import wrds  # pyrefly: ignore[missing-import]  (optional dependency: pip install wrds)

    db = wrds.Connection()  # prompts for credentials

    ff = db.raw_sql("select date, mktrf, smb, hml, umd, rf from ff.factors_monthly where date >= %(s)s",
                    params={"s": START}, date_cols=["date"])
    ff.to_csv(CACHE / "wrds_ff_factors.csv", index=False)
    print(f"Fama-French factors: {len(ff)} months")

    tickers = tuple(ETFS)
    try:  # CRSP CIZ format (current)
        crsp = db.raw_sql(
            """select b.ticker, a.mthcaldt as date, a.mthret as ret
               from crsp.msf_v2 a join crsp.stksecurityinfohist b
                 on a.permno = b.permno and a.mthcaldt between b.secinfostartdt and b.secinfoenddt
               where b.ticker in %(t)s and a.mthcaldt >= %(s)s""",
            params={"t": tickers, "s": START}, date_cols=["date"])
    except Exception as e:  # legacy SIZ tables
        print("CIZ query failed, using legacy crsp.msf:", e)
        crsp = db.raw_sql(
            """select b.ticker, a.date, a.ret from crsp.msf a join crsp.msenames b
                 on a.permno = b.permno and a.date between b.namedt and b.nameendt
               where b.ticker in %(t)s and a.date >= %(s)s""",
            params={"t": tickers, "s": START}, date_cols=["date"])
    crsp = crsp.dropna(subset=["ret"])
    crsp["date"] = pd.to_datetime(crsp["date"]).dt.to_period("M").dt.to_timestamp()
    wide = crsp.pivot_table(index="date", columns="ticker", values="ret", aggfunc="first").reset_index()
    wide.to_csv(CACHE / "wrds_crsp_monthly.csv", index=False)
    print(f"CRSP: {len(wide)} months x {wide.shape[1] - 1} tickers")
    db.close()


if __name__ == "__main__":
    main()
