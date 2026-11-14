"""SQL logic behind every Tableau case, as functions over SQL source expressions.

Used by scripts/reconcile.py (real data) and tests/test_queries.py (tiny fixtures),
so the same logic is verified on both. Each `src` argument is a DuckDB table
expression, e.g. read_csv('...') or read_xlsx('...').
"""
from pathlib import Path


def csv(path):
    """All-varchar CSV source (dates stay text so they can be parsed explicitly)."""
    return f"read_csv('{Path(path).as_posix()}', all_varchar=true)"


# ---- case 01: Olympics. "NA" is a text string in the CSV, not NULL. Group by ID, never by Name.
def olympics(con, src):
    total = con.execute(f"select count(*) from {src}").fetchone()[0]
    rows = con.execute(
        f"""with p as (select ID, sum(case when Medal <> 'NA' then 1 else 0 end) m from {src} group by ID)
            select m, count(*) from p group by m"""
    ).fetchall()
    return {"total_rows": total, "athletes_by_medals": {int(m): n for m, n in rows}}


# ---- case 02: Olist cohort. Dates are dd/m/yy h:mm.
# Cohort = MIN purchase year over ALL orders (LEFT JOIN items), not only orders that have items.
def olist_cohort(con, orders, customers, items):
    rows = con.execute(
        f"""
with o as (select order_id, customer_id, strptime(order_purchase_timestamp, '%d/%m/%y %H:%M') ts from {orders}),
     cu as (select customer_id, customer_unique_id from {customers}),
     it as (select order_id, try_cast(price as double) price from {items}),
     oc as (select o.order_id, cu.customer_unique_id cid, o.ts from o join cu using (customer_id)),
     coh as (select cid, min(year(ts)) cy from oc group by cid),
     s as (select year(oc.ts) oy, coh.cy, it.price from oc join coh using (cid) left join it using (order_id))
select cy, oy, coalesce(sum(price), 0) from s group by all order by 1, 2"""
    ).fetchall()
    return {(cy, oy): v for cy, oy, v in rows}


# ---- case 03: LeBron weekly KPI. Tableau weeks start on SUNDAY; DuckDB date_trunc('week') starts on MONDAY.
def lebron(con, src, expert, above_average):
    base = f"""
g as (select Season, strptime(Date, '%d/%m/%y')::date d, try_cast(GameScore as double) gs from {src}),
g2 as (select *, date_trunc('week', d + 1)::date - 1 ws from g)"""
    rows = con.execute(
        f"""with {base},
w as (select *, avg(gs) over (partition by ws) av from g2),
k as (select distinct Season, ws,
             case when av > {expert} then 'Expert'
                  when av > {above_average} then 'Above Average'
                  else 'Below Average' end cat from w)
select Season, count(*) filter (cat = 'Expert'), count(*) filter (cat = 'Above Average'),
       count(*) filter (cat = 'Below Average') from k group by Season order by Season"""
    ).fetchall()
    tw, nul = con.execute(
        f"""with {base}
select count(distinct ws), count(*) filter (c = 0) from (select ws, count(gs) c from g2 group by ws)"""
    ).fetchone()
    mean, nn = con.execute(f"with {base} select avg(gs), count(*) filter (gs is null) from g").fetchone()
    return {
        "per_season": {r[0]: list(r[1:]) for r in rows},
        "total_weeks": tw,
        "weeks_all_null": nul,
        "mean_game_score": mean,
        "null_scores": nn,
    }


# ---- case 04: World Bank. One year only (the file holds many); SUM ignores NULL GDP.
def worldbank(con, src, year):
    base = f"""
t as (select "Country Name" country, Region region, try_cast("GDP (USD)" as double) gdp
      from {src} where try_cast(Year as int) = {year})"""
    total, n, reg, nul = con.execute(
        f"""with {base}
select sum(gdp), count(*), count(distinct region), count(*) filter (gdp is null) from t"""
    ).fetchone()
    shares = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            f"""with {base},
r as (select *, sum(gdp) over (partition by region) rt, sum(gdp) over () gt from t)
select country, 100 * gdp / gt, 100 * gdp / rt from r"""
        ).fetchall()
    }
    return {"total": total, "countries": n, "regions": reg, "null_gdp": nul, "shares": shares}


# ---- case 05: Jordan free throws vs a baseline season (EXCLUDE LOD). One row per season, regular + playoffs together.
# Mirrors Tableau: _FT Selected_season = IIF(Season = baseline, FT, 0); LOD = { EXCLUDE Season : SUM(that) } is the
# same number on every row; difference = SUM(FT) - LOD. SUM ignores NULL FT (rows like "Did Not Dress").
def jordan(con, src, baseline):
    t = f"""t as (select Season, Stage, try_cast("Free Throws" as double) ft from {src})"""
    rows = con.execute(
        f"""with {t},
s as (select Season, sum(ft) ft, sum(case when Season = ? then ft else 0 end) sel from t group by Season)
select Season, ft, ft - sum(sel) over () from s order by Season""",
        [baseline],
    ).fetchall()
    n, nul, seasons, total, playoffs = con.execute(
        f"""with {t}
select count(*), count(*) filter (ft is null), count(distinct Season), sum(ft),
       sum(ft) filter (Stage = 'Playoffs') from t"""
    ).fetchone()
    return {
        "ft_by_season": {r[0]: r[1] for r in rows},
        "diff": {r[0]: r[2] for r in rows},
        "rows": n,
        "null_ft_rows": nul,
        "seasons": seasons,
        "total_ft": total,
        "playoff_ft": playoffs,
    }
