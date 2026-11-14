# Tableau business cases: LOD expressions, verified against SQL

Work in progress. Each case has the question, the Tableau formulas, the gotchas found, and the same numbers reproduced in SQL (DuckDB).

| # | Case | Technique | Headline number |
|---|---|---|---|
| 01 | [Olympic medals frequency](cases/01-olympics-medal-frequency) | FIXED LOD per athlete | 215 athletes with 5 medals |
| 02 | [Olist returning customers](cases/02-olist-cohort) | FIXED LOD cohort (MIN order date) | 1,443,090 total |
| 03 | [LeBron weekly performance KPI](cases/03-lebron-weekly-kpi) | FIXED LOD + parameters | 504 weeks, 10 with no data |
| 04 | [World regional GDP share](cases/04-worldbank-pct-total) | FIXED LOD percent of total | 83.9T USD (2018) |

## Verify the numbers
```
uv run scripts/reconcile.py     # recomputes every Tableau control value in DuckDB (41 checks)
```
Control values live in `controls.yaml`, and each case README lists the gotchas the SQL check exposed.

Raw data is not in the repo: see `data/manifest.yaml`.

## Data and attribution
- Olist: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), CC BY-NC-SA 4.0 (non-commercial, share-alike).
- Olympics: [120 years of Olympic history](https://www.kaggle.com/datasets/heesoo37/120-years-of-olympic-history-athletes-and-results) (Kaggle, scraped from sports-reference.com).
- World Bank indicators: [data.worldbank.org](https://data.worldbank.org/), CC BY 4.0 by default.
- LeBron James career stats: course material; the workbook for case 03 is not published here.

Practice built on the SuperDataScience course "Tableau Business Cases: LOD Expressions". Checksums and sources are in `data/manifest.yaml`.
