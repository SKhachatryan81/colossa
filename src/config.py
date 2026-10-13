"""Central settings. Edit the query lists to point the tool at your niche."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("PS_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "signals.duckdb"
RAW_DIR = DATA_DIR / "raw"

USER_AGENT = "painsignals/0.1 (personal research tool)"

# Phrases that tend to appear when someone describes a real problem.
# Used for Hacker News and Reddit search (quoted as exact phrases).
PHRASE_QUERIES = [
    "is there a tool",
    "is there a way to",
    "alternative to",
    "we do this manually",
    "in a spreadsheet",
    "waste hours",
    "sick of",
    "how do you handle",
]

# GitHub issue search queries (DevOps-flavoured). Date window is added automatically.
GITHUB_QUERIES = [
    '"workaround" kubernetes',
    '"manually" terraform',
    '"is there a way to" helm',
    '"painful" "ci/cd"',
    '"tedious" deployment',
    '"we currently" "manually" infrastructure',
]

REDDIT_SUBREDDITS = ["devops", "kubernetes", "sysadmin", "terraform", "googlecloud"]
