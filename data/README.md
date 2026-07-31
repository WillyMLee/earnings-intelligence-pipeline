# data/

Runtime-generated, not source. `pipelines/fetch_earnings_calendar.py` writes
`latest_earnings_calendar.csv` here (via `ensure_calendar_csv()` in the entry
scripts, which self-regenerates it if missing -- see the README's note on
ephemeral cron containers for why that self-healing exists). The CSV itself
is gitignored; only this placeholder is tracked so the directory exists.
