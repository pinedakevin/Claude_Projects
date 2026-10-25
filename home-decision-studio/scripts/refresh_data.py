"""Refresh the data behind Home Decision Studio.

Runs weekly from GitHub Actions (.github/workflows/refresh-home-decision-studio.yml).
It updates only what has a reliable public data file:

  * Home values  - Zillow Home Value Index city files (3-bed, 4-bed, single-family, all homes)
  * Mortgage rates - Freddie Mac's weekly survey (30- and 15-year fixed), via FRED

VA and FHA rates have no public feed, so they move with the Freddie Mac 30-year rate,
keeping the gap measured from real quotes in Oct 2026 (see SPREADS below). Rents, crime,
schools, census figures and drive times are updated by hand.

Each source is refreshed independently: if one download fails, the rest still update
and the old numbers for the failed source are kept.

Usage:  python home-decision-studio/scripts/refresh_data.py
Set ZILLOW_DIR to a folder of already-downloaded Zillow CSVs to skip the downloads (testing).
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "home-decision-studio-refresh (github.com/pinedakevin/Claude_Projects)"}

ZILLOW_BASE = "https://files.zillowstatic.com/research/public_csvs/zhvi/"
ZILLOW_FILES = {
    "zhvi_3bd": "City_zhvi_bdrmcnt_3_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "zhvi_4bd": "City_zhvi_bdrmcnt_4_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "zhvi_sfr": "City_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv",
    "zhvi_all_homes": "City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
}

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

# Gaps (percentage points) between each loan's rate and Freddie Mac's conventional rate,
# measured from real quotes on Oct 22-24, 2026. Update these when you re-check quotes.
SPREADS = {
    "va_rate": ("conv_rate", -0.32),      # VA 30-yr 7.00% vs conventional 7.32%
    "fha_rate": ("conv_rate", -0.15),     # FHA 30-yr 7.17% vs conventional 7.32%
    "va_rate_15": ("va_rate", -0.38),     # 15-yr VA discount seen in VA quotes
    "fha_rate_15": ("fha_rate", -0.38),   # same discount applied to FHA (estimate)
}


def log(msg: str) -> None:
    print(f"[refresh] {msg}", flush=True)


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def write_csv(path: Path, cols: list[str], rows: list[dict], value_cols: list[str]) -> bool:
    """Write the file only if a value changed; return True when it did."""
    _, old = read_csv(path)
    def norm(v):
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return str(v)

    key = lambda rs: [[norm(r[c]) for c in value_cols] for r in rs]
    if key(old) == key(rows):
        return False
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return True


def zillow_text(name: str) -> str:
    local = os.environ.get("ZILLOW_DIR")
    if local:
        return (Path(local) / name).read_text(encoding="utf-8")
    r = requests.get(ZILLOW_BASE + name, headers=HEADERS, timeout=300)
    r.raise_for_status()
    return r.text


def refresh_home_values(meta: dict) -> bool:
    path = DATA / "home_values.csv"
    cols, rows = read_csv(path)
    wanted = {(r["city"], r["county"]) for r in rows}
    found: dict[str, dict] = {}
    month = None
    for key, name in ZILLOW_FILES.items():
        log(f"Zillow: {name}")
        reader = csv.reader(io.StringIO(zillow_text(name)))
        header = next(reader)
        dates = [i for i, h in enumerate(header) if h[:2] == "20"]
        ix = {h: i for i, h in enumerate(header)}
        for rec in reader:
            if rec[ix["State"]] != "UT":
                continue
            county = rec[ix["CountyName"]].replace(" County", "")
            if (rec[ix["RegionName"]], county) not in wanted:
                continue
            filled = [i for i in dates if rec[i]]
            if not filled:
                continue
            last = filled[-1]
            out = found.setdefault(rec[ix["RegionName"]], {})
            out[key] = round(float(rec[last]))
            out["_month"] = header[last][:7]
            if key == "zhvi_sfr":
                prev = dates.index(last) - 12
                if prev >= 0 and rec[dates[prev]]:
                    out["zhvi_sfr_sep2025"] = round(float(rec[dates[prev]]))
    missing = [r["city"] for r in rows if r["city"] not in found or len(found[r["city"]]) < 6]
    if missing:
        raise RuntimeError(f"Zillow data missing for: {', '.join(missing)}")
    for r in rows:
        f = found[r["city"]]
        for k in ("zhvi_3bd", "zhvi_4bd", "zhvi_sfr", "zhvi_all_homes", "zhvi_sfr_sep2025"):
            r[k] = f[k]
        r["month"] = f["_month"]
        month = f["_month"]
    if not write_csv(path, cols, rows, ["month", "zhvi_3bd", "zhvi_4bd", "zhvi_sfr", "zhvi_all_homes"]):
        log(f"Home values unchanged ({month})")
        return False
    meta["sources"]["Home values"] = "Zillow, " + datetime.strptime(month, "%Y-%m").strftime("%b %Y")
    log(f"Home values updated through {month}")
    return True


def fred_latest(series: str) -> tuple[str, float]:
    r = requests.get(FRED.format(series), headers=HEADERS, timeout=60)
    r.raise_for_status()
    rows = [row for row in csv.reader(io.StringIO(r.text))][1:]
    rows = [row for row in rows if len(row) >= 2 and row[1] not in ("", ".")]
    date, value = rows[-1][0], float(rows[-1][1])
    return date, value


def refresh_rates(meta: dict) -> bool:
    path = DATA / "mortgage_inputs.csv"
    cols, rows = read_csv(path)
    by_key = {r["key"]: r for r in rows}
    d30, conv30 = fred_latest("MORTGAGE30US")
    d15, conv15 = fred_latest("MORTGAGE15US")
    week = datetime.strptime(d30, "%Y-%m-%d").strftime("%b %-d, %Y")
    by_key["conv_rate"]["value"] = f"{conv30:.2f}"
    by_key["conv_rate"]["source"] = f"Freddie Mac PMMS via FRED, week of {week}"
    by_key["conv_rate_15"]["value"] = f"{conv15:.2f}"
    by_key["conv_rate_15"]["source"] = f"Freddie Mac PMMS via FRED, week of {week}"
    for key, (base, gap) in SPREADS.items():
        if key in by_key:
            by_key[key]["value"] = f"{float(by_key[base]['value']) + gap:.2f}"
            by_key[key]["source"] = f"Estimated: {base.replace('_', ' ')} {gap:+.2f} pt (gap measured from Oct 2026 quotes), week of {week}"
    if not write_csv(path, cols, rows, ["key", "value"]):
        log(f"Rates unchanged (week of {week})")
        return False
    meta["sources"]["Mortgage rates"] = f"Freddie Mac week of {week}; VA and FHA estimated from it"
    log(f"Rates updated: 30-yr {conv30:.2f}%, 15-yr {conv15:.2f}% (week of {week})")
    return True


def main() -> int:
    meta_path = DATA / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("sources", {})
    changed = False
    for name, fn in (("home values", refresh_home_values), ("mortgage rates", refresh_rates)):
        try:
            changed = fn(meta) or changed
        except Exception as e:  # keep going; old data stays in place
            log(f"Skipped {name}: {e}")
    if changed:
        meta["refreshed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log("Done" if changed else "Nothing updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
