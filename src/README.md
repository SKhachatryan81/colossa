# painsignals (local)

Collects public posts, scores them with cheap keyword rules, optionally runs an LLM on the best ones, and reports likely pain signals. Everything lives in `data/` (DuckDB file plus raw JSON).

## Setup
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Optional environment variables:
- `GITHUB_TOKEN`: a personal access token (no scopes needed). Without it GitHub search is very slow.
- `ANTHROPIC_API_KEY`: needed only for `extract`.
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`: only once Reddit approves your app.

## Run
```
python main.py collect --sources hn,github --days 7
python main.py report --no-llm            # read the top posts yourself first
python main.py extract --dry-run          # see how many posts the LLM would read
python main.py extract --limit 50
python main.py report                     # LLM-extracted signals
python main.py report --csv signals.csv
```

## Tuning
- `config.py`: search phrases, GitHub queries, subreddits.
- `score.py`: keyword weights. After editing, run `python main.py score --rescore`.
- Query the DB directly: `duckdb data/signals.duckdb`.

## Notes
- Check each site's terms before heavy use; this is meant for small personal research runs.
- Posts are stored without usernames on purpose.
