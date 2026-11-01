"""Download NSE cash-market bhavcopies for one calendar year and save one compact parquet.

Old format (to early Jul 2024): content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip
UDiFF format (from Jul 2024):   content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
Both carry the exchange's previous close, which NSE adjusts on ex-dates (splits,
bonus, rights) - the analysis uses that to adjust prices, so no separate
corporate-action feed is needed.

Usage: python fetch_bhavcopy.py 2015 out_dir
"""
import datetime as dt
import io
import os
import random
import sys
import time
import zipfile

import pandas as pd
import requests

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36", "Referer": "https://www.nseindia.com/", "Accept": "*/*"}
BASE = "https://nsearchives.nseindia.com"
SERIES = {"EQ", "BE", "BZ", "BT", "SM", "ST", "SZ"}
UDIFF_FROM = dt.date(2024, 7, 8)


def urls(d):
    old = f"{BASE}/content/historical/EQUITIES/{d.year}/{d.strftime('%b').upper()}/cm{d.strftime('%d%b%Y').upper()}bhav.csv.zip"
    new = f"{BASE}/content/cm/BhavCopy_NSE_CM_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    return [new, old] if d >= UDIFF_FROM else [old, new]


def parse(raw, d):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]))
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:
        df = df.rename(columns={"TckrSymb": "symbol", "SctySrs": "series", "ISIN": "isin", "HghPric": "high",
                                "LwPric": "low", "ClsPric": "close", "PrvsClsgPric": "prevclose",
                                "TtlTrfVal": "value"})
    else:
        df = df.rename(columns={"SYMBOL": "symbol", "SERIES": "series", "ISIN": "isin", "HIGH": "high",
                                "LOW": "low", "CLOSE": "close", "PREVCLOSE": "prevclose", "TOTTRDVAL": "value"})
    df["series"] = df["series"].astype(str).str.strip()
    df = df[df["series"].isin(SERIES)]
    out = df[["symbol", "series", "isin", "high", "low", "close", "prevclose", "value"]].copy()
    out["date"] = pd.Timestamp(d)
    return out


def main(year, out_dir):
    s = requests.Session()
    s.headers.update(HEAD)
    try:
        s.get("https://www.nseindia.com/", timeout=20)
    except Exception:  # noqa: BLE001
        pass
    start, end = dt.date(year, 1, 1), min(dt.date(year, 12, 31), dt.date.today() - dt.timedelta(days=1))
    frames, missing, d = [], [], start
    while d <= end:
        if d.weekday() < 5:
            got = False
            for u in urls(d):
                for attempt in range(4):
                    try:
                        r = s.get(u, timeout=30)
                    except Exception:  # noqa: BLE001
                        time.sleep(3 * (attempt + 1))
                        continue
                    if r.status_code == 200 and r.content[:2] == b"PK":
                        frames.append(parse(r.content, d))
                        got = True
                    elif r.status_code in (403, 429, 503):
                        time.sleep(10 * (attempt + 1))
                        continue
                    break
                if got:
                    break
            if not got:
                missing.append(d.isoformat())   # holidays land here too
            time.sleep(random.uniform(0.3, 0.8))
        d += dt.timedelta(days=1)
    os.makedirs(out_dir, exist_ok=True)
    if frames:
        df = pd.concat(frames, ignore_index=True)
        for c in ("symbol", "series", "isin"):
            df[c] = df[c].astype(str).str.strip().astype("category")
        for c in ("high", "low", "close", "prevclose", "value"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        df.to_parquet(os.path.join(out_dir, f"prices_{year}.parquet"), compression="zstd", index=False)
        print(f"{year}: {df['date'].nunique()} trading days, {len(df):,} rows")
    with open(os.path.join(out_dir, f"missing_{year}.txt"), "w") as f:
        f.write("\n".join(missing))
    print(f"{year}: {len(missing)} weekdays without a file (holidays or gaps)")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
