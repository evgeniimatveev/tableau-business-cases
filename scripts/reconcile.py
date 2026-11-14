# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb", "pyyaml"]
# ///
"""Recompute Tableau control values in SQL (DuckDB) and compare to controls.yaml.

Run: uv run scripts/reconcile.py   (exit code 1 if any check fails)
"""
import sys
from pathlib import Path
import duckdb
import yaml

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


# ---- case 01: Olympics (FIXED per athlete ID; "NA" is a string, not NULL)
oly = f"read_csv('{RAW / 'athlete_events.csv'}', all_varchar=true)"
total = con.execute(f"select count(*) from {oly}").fetchone()[0]
per = con.execute(f"""with p as (select ID, sum(case when Medal <> 'NA' then 1 else 0 end) m from {oly} group by ID)
                  select count(*) filter (m=5), count(*) filter (m=6), count(*) filter (m>=7) from p""").fetchone()
o = ctl["olympics"]
check("01 olympics", "total_rows", o["total_rows"], total)
check("01 olympics", "athletes_with_5_medals", o["athletes_with_5_medals"], per[0])
check("01 olympics", "athletes_with_6_medals", o["athletes_with_6_medals"], per[1])
check("01 olympics", "athletes_with_7plus_medals", o["athletes_with_7plus_medals"], per[2])

# ---- case 02: Olist cohort. Dates are dd/m/yy h:mm. LEFT JOIN items: cohort = MIN over ALL orders.
con.execute(f"""
create view o as select order_id, customer_id, strptime(order_purchase_timestamp,'%d/%m/%y %H:%M') ts
  from read_csv('{RAW / 'olist_orders_dataset.csv'}', all_varchar=true);
create view cu as select customer_id, customer_unique_id
  from read_csv('{RAW / 'olist_customers_dataset.csv'}', all_varchar=true);
create view it as select order_id, try_cast(price as double) price
  from read_csv('{RAW / 'olist_order_items_dataset.csv'}', all_varchar=true);
""")
rows = con.execute("""
with oc as (select o.order_id, cu.customer_unique_id cid, o.ts from o join cu using(customer_id)),
     coh as (select cid, min(year(ts)) cy from oc group by cid),
     s as (select year(oc.ts) oy, coh.cy, it.price from oc join coh using(cid) left join it using(order_id))
select cy, oy, sum(price) from s group by all order by 1, 2""").fetchall()
got = {(a, b): v for a, b, v in rows}
c2 = ctl["olist_cohort"]
check("02 olist", "total", c2["total"], sum(got.values()), tol=0.5)
for cy, oy, exp in c2["matrix"]:
    check("02 olist", f"cohort {cy} in {oy}", exp, got.get((cy, oy), 0), tol=0.5)

# ---- case 03: LeBron weekly KPI. Tableau week starts SUNDAY (DuckDB date_trunc('week') = Monday), dates dd/m/yy.
l = ctl["lebron"]
th = l["thresholds"]
con.execute(f"""
create view g as select Season, strptime(Date,'%d/%m/%y')::date d, try_cast(GameScore as double) gs
  from read_csv('{RAW / 'LeBron James Career.csv'}', all_varchar=true);
create view g2 as select *, date_trunc('week', d + 1)::date - 1 ws from g;
""")
rows = con.execute(f"""
with w as (select *, avg(gs) over (partition by ws) av from g2),
     k as (select distinct Season, ws, case when av > {th['expert']} then 'Expert'
                                          when av > {th['above_average']} then 'Above Average'
                                          else 'Below Average' end cat from w)
select Season, count(*) filter (cat='Expert'), count(*) filter (cat='Above Average'),
       count(*) filter (cat='Below Average') from k group by Season order by Season""").fetchall()
got = {r[0]: list(r[1:]) for r in rows}
for season, exp in l["per_season"].items():
    ok = got.get(season) == exp
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {'03 lebron':<12} {season:<34} expected={exp} sql={got.get(season)}")
tw, nul = con.execute("select count(distinct ws), count(*) filter (c = 0) from (select ws, count(gs) c from g2 group by ws)").fetchone()
check("03 lebron", "total_weeks", l["total_weeks"], tw)
mean, nn = con.execute("select avg(gs), count(*) filter (gs is null) from g").fetchone()
check("03 lebron", "overall_mean_game_score", l["overall_mean_game_score"], round(mean, 2), tol=0.005)
check("03 lebron", "null_game_scores", l["null_game_scores"], nn)
check("03 lebron", "weeks_with_all_null_game_score", l["weeks_with_all_null_game_score"], nul)

# ---- case 04: WorldBank (file has 1960-2018; the workbook is on 2018)
wb = f"read_xlsx('{RAW / 'WorldBank Data.xlsx'}')"
w = ctl["worldbank"]
y = w["year"]
tot, fr, n, reg, nul = con.execute(f"""
with t as (select * from {wb} where Year = {y})
select sum("GDP (USD)"),
       100 * (select "GDP (USD)" from t where "Country Name" = 'France') / sum("GDP (USD)"),
       count(*), count(distinct Region), count(*) filter ("GDP (USD)" is null)
from t""").fetchone()
check("04 worldbank", "total_gdp_usd", w["total_gdp_usd"], tot, tol=1)
check("04 worldbank", "france_share_pct", w["france_share_pct"], round(fr, 2), tol=0.005)
sh = {r[0]: (r[1], r[2]) for r in con.execute(f"""
with t as (select * from {wb} where Year = {y}),
     r as (select *, sum("GDP (USD)") over (partition by Region) rt, sum("GDP (USD)") over () gt from t)
select "Country Name", 100*"GDP (USD)"/gt, 100*"GDP (USD)"/rt from r
where "Country Name" in ('China','Japan','United States')""").fetchall()}
check("04 worldbank", "china_share_global_pct", w["china_share_global_pct"], round(sh["China"][0], 2), tol=0.005)
check("04 worldbank", "usa_share_global_pct", w["usa_share_global_pct"], round(sh["United States"][0], 2), tol=0.005)
check("04 worldbank", "china_share_of_region_pct", w["china_share_of_region_pct"], sh["China"][1], tol=1e-5)
check("04 worldbank", "japan_share_of_region_pct", w["japan_share_of_region_pct"], sh["Japan"][1], tol=1e-5)
check("04 worldbank", "countries", w["countries"], n)
check("04 worldbank", "regions", w["regions"], reg)
check("04 worldbank", "countries_null_gdp", w["countries_null_gdp"], nul)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
