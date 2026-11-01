"""Download NSE equity corporate actions (bonus, split, consolidation, rights...) 2010 to date.
Saves data/corp_actions.csv. Uses NSE's public website API, one quarter at a time."""
import datetime as dt
import json
import os
import random
import time

import pandas as pd
import requests

HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36", "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions"}
API = "https://www.nseindia.com/api/corporates-corporateActions"


def session():
    s = requests.Session()
    s.headers.update(HEAD)
    s.get("https://www.nseindia.com/", timeout=30)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-actions", timeout=30)
    return s


def main():
    s, rows = session(), []
    d = dt.date(2010, 1, 1)
    today = dt.date.today()
    while d <= today:
        e = min(dt.date(d.year + (d.month + 2) // 12, (d.month + 2) % 12 + 1, 1) - dt.timedelta(days=1), today)
        for kind in ("equities", "sme"):
            params = {"index": kind, "from_date": d.strftime("%d-%m-%Y"), "to_date": e.strftime("%d-%m-%Y")}
            for attempt in range(5):
                try:
                    r = s.get(API, params=params, timeout=60)
                    if r.status_code == 200 and r.text.strip().startswith("["):
                        data = r.json()
                        for x in data:
                            x["_index"] = kind
                        rows += data
                        print(d, e, kind, len(data), flush=True)
                        break
                    print(d, kind, "HTTP", r.status_code, r.text[:80])
                except Exception as ex:  # noqa: BLE001
                    print(d, kind, "error", ex)
                time.sleep(5 * (attempt + 1))
                s = session()
            time.sleep(random.uniform(1, 2))
        d = e + dt.timedelta(days=1)
    os.makedirs("data", exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv("data/corp_actions.csv", index=False)
    print("saved", len(df), "rows; columns:", list(df.columns))


if __name__ == "__main__":
    main()
