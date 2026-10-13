PY = .venv/bin/python

collect:
	$(PY) main.py collect --sources hn,github --days 7

top:
	$(PY) main.py report --no-llm --top 20

estimate:
	$(PY) main.py extract --dry-run

extract:
	$(PY) main.py extract --limit 50

report:
	$(PY) main.py report --csv signals.csv