# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb", "pyyaml"]
# ///
"""Recompute Tableau control values in SQL (DuckDB) and compare to controls.yaml.

Run: uv run scripts/reconcile.py   (exit code 1 if any check fails)
The SQL itself lives in scripts/queries.py (also unit-tested on tiny fixtures, see tests/).
"""
import sys
from pathlib import Path

import duckdb
import yaml

import queries as q

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
ctl = yaml.safe_load((ROOT / "controls.yaml").read_text(encoding="utf-8"))

con = duckdb.connect()
con.execute("INSTALL excel; LOAD excel")
results = []


def check(case, name, expected, actual, tol=0.0):
    ok = abs(float(expected) - float(actual)) <= tol
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {case:<12} {name:<34} expected={expected:<18} sql={actual}")


skipped = []


def have(files, case):
    """Run a case only if its raw files are in data/raw/ (they are not committed, see README "Get the data")."""
    missing = [f for f in files if not (RAW / f).exists()]
    if missing:
        skipped.append(case)
        print(f"SKIP case {case}: missing data/raw/{', data/raw/'.join(missing)}")
    return not missing


# ---- case 01: Olympics
if have(['athlete_events.csv'], "01"):
    o = ctl["olympics"]
    r = q.olympics(con, q.csv(RAW / "athlete_events.csv"))
    by = r["athletes_by_medals"]
    check("01 olympics", "total_rows", o["total_rows"], r["total_rows"])
    check("01 olympics", "athletes_with_5_medals", o["athletes_with_5_medals"], by.get(5, 0))
    check("01 olympics", "athletes_with_6_medals", o["athletes_with_6_medals"], by.get(6, 0))
    check("01 olympics", "athletes_with_7plus_medals", o["athletes_with_7plus_medals"],
          sum(n for m, n in by.items() if m >= 7))

# ---- case 02: Olist cohort
if have(['olist_orders_dataset.csv', 'olist_customers_dataset.csv', 'olist_order_items_dataset.csv'], "02"):
    c2 = ctl["olist_cohort"]
    got = q.olist_cohort(
        con,
        q.csv(RAW / "olist_orders_dataset.csv"),
        q.csv(RAW / "olist_customers_dataset.csv"),
        q.csv(RAW / "olist_order_items_dataset.csv"),
    )
    check("02 olist", "total", c2["total"], sum(got.values()), tol=0.5)
    for cy, oy, exp in c2["matrix"]:
        check("02 olist", f"cohort {cy} in {oy}", exp, got.get((cy, oy), 0), tol=0.5)

# ---- case 03: LeBron
if have(['LeBron James Career.csv'], "03"):
    l = ctl["lebron"]
    th = l["thresholds"]
    r = q.lebron(con, q.csv(RAW / "LeBron James Career.csv"), th["expert"], th["above_average"])
    for season, exp in l["per_season"].items():
        ok = r["per_season"].get(season) == exp
        results.append(ok)
        print(f"{'OK  ' if ok else 'FAIL'} {'03 lebron':<12} {season:<34} expected={exp} sql={r['per_season'].get(season)}")
    check("03 lebron", "total_weeks", l["total_weeks"], r["total_weeks"])
    check("03 lebron", "overall_mean_game_score", l["overall_mean_game_score"], round(r["mean_game_score"], 2), tol=0.005)
    check("03 lebron", "null_game_scores", l["null_game_scores"], r["null_scores"])
    check("03 lebron", "weeks_with_all_null_game_score", l["weeks_with_all_null_game_score"], r["weeks_all_null"])

# ---- case 04: World Bank (file has 1960-2018; the workbook filters Year to 2018)
if have(['WorldBank Data.xlsx'], "04"):
    w = ctl["worldbank"]
    r = q.worldbank(con, f"read_xlsx('{(RAW / 'WorldBank Data.xlsx').as_posix()}')", w["year"])
    sh = r["shares"]
    check("04 worldbank", "total_gdp_usd", w["total_gdp_usd"], r["total"], tol=1)
    check("04 worldbank", "france_share_pct", w["france_share_pct"], round(sh["France"][0], 2), tol=0.005)
    check("04 worldbank", "china_share_global_pct", w["china_share_global_pct"], round(sh["China"][0], 2), tol=0.005)
    check("04 worldbank", "usa_share_global_pct", w["usa_share_global_pct"], round(sh["United States"][0], 2), tol=0.005)
    check("04 worldbank", "china_share_of_region_pct", w["china_share_of_region_pct"], sh["China"][1], tol=1e-5)
    check("04 worldbank", "japan_share_of_region_pct", w["japan_share_of_region_pct"], sh["Japan"][1], tol=1e-5)
    check("04 worldbank", "countries", w["countries"], r["countries"])
    check("04 worldbank", "regions", w["regions"], r["regions"])
    check("04 worldbank", "countries_null_gdp", w["countries_null_gdp"], r["null_gdp"])

# ---- case 05: Jordan free throws vs baseline season (EXCLUDE LOD)
if have(['Michael Jordan Career.csv'], "05"):
    j = ctl["jordan"]
    r = q.jordan(con, q.csv(RAW / "Michael Jordan Career.csv"), j["baseline"])
    for key in ("rows", "null_ft_rows", "seasons", "total_ft", "playoff_ft"):
        check("05 jordan", key, j[key], r[key])
    for season, exp in j["ft_by_season"].items():
        check("05 jordan", f"FT {season}", exp, r["ft_by_season"].get(season, -1))
    for season, exp in j["diff_from_baseline"].items():
        check("05 jordan", f"diff {season}", exp, r["diff"].get(season, -1))

    # the parameter is a dropdown of all 15 seasons: for EVERY choice the baseline bar is 0 and every other bar is FT - baseline FT
    # (self-consistency of the toggle; only the 1984-85 values above were read off Tableau)
    for base in j["ft_by_season"]:
        rb = q.jordan(con, q.csv(RAW / "Michael Jordan Career.csv"), base)
        ok = rb["diff"][base] == 0 and all(
            rb["diff"][s] == rb["ft_by_season"][s] - rb["ft_by_season"][base] for s in rb["ft_by_season"]
        )
        check("05 jordan", f"toggle baseline {base}", 1, int(ok))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


