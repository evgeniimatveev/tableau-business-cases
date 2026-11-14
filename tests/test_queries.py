"""SQL logic tests on tiny hand-computed fixtures. Each test guards one Tableau gotcha."""
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import queries as q  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def con():
    return duckdb.connect()


def test_olympics_groups_by_id_and_treats_na_as_text(con):
    r = q.olympics(con, q.csv(FX / "olympics.csv"))
    assert r["total_rows"] == 6
    # ID 1 has 2 medals ("NA" row is not a medal); IDs 3 and 4 share the name "John Smith" but are 2 athletes with 1 medal each.
    # Grouping by Name would merge them into one "John Smith" with 2 medals and report {0: 1, 2: 2}.
    assert r["athletes_by_medals"] == {0: 1, 1: 2, 2: 1}


def test_cohort_uses_left_join_so_orders_without_items_set_the_cohort_year(con):
    got = q.olist_cohort(
        con, q.csv(FX / "olist_orders.csv"), q.csv(FX / "olist_customers.csv"), q.csv(FX / "olist_items.csv")
    )
    # u1's first order (2016) was canceled and has no items. The cohort is still 2016.
    # An INNER JOIN would move u1 to the 2017 cohort and give (2017, 2017) = 175.
    assert got == {(2016, 2016): 0, (2016, 2017): 100, (2017, 2017): 75, (2017, 2018): 10, (2018, 2018): 40}
    assert sum(got.values()) == 225


def test_lebron_weeks_start_on_sunday_and_boundaries_are_strict(con):
    r = q.lebron(con, q.csv(FX / "lebron.csv"), expert=30, above_average=20)
    # Weeks (Sunday start): Dec 14 avg 25 -> Above; Dec 21 no scores -> ELSE; Dec 28 avg 30 -> exactly 30 is not Expert.
    # With Monday-start weeks the Sunday 28/12 game would join the Dec 22 week (avg 35 -> Expert) and this fails.
    assert r["per_season"] == {"2003-04": [0, 2, 1]}
    assert r["total_weeks"] == 3


def test_lebron_week_without_scores_is_counted_and_lands_in_below_average(con):
    r = q.lebron(con, q.csv(FX / "lebron.csv"), expert=30, above_average=20)
    assert r["weeks_all_null"] == 1  # the week of Dec 21: its only game has no score
    assert r["null_scores"] == 1
    assert r["mean_game_score"] == pytest.approx(27.5)  # NULL ignored: (30+20+35+25)/4


def test_worldbank_restricts_to_one_year_and_ignores_null_gdp(con):
    r = q.worldbank(con, f"read_csv('{(FX / 'worldbank.csv').as_posix()}')", 2018)
    assert r["total"] == 1000  # 2017 rows are excluded
    assert (r["countries"], r["regions"], r["null_gdp"]) == (4, 2, 1)
    glob_x, reg_x = r["shares"]["X"]
    assert glob_x == pytest.approx(60.0)  # share of the world
    assert reg_x == pytest.approx(600 / 900 * 100)  # share of region A (the NULL country is not in the total)
    assert r["shares"]["Z"] == (None, None)  # NULL GDP gives a NULL share, not 0%
