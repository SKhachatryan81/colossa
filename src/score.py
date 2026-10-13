"""Cheap keyword scoring. Runs before any LLM so you only pay to analyse promising posts."""
import re

# (regex, weight, label). Positive = pain/spend signal, negative = noise (promo, students).
PATTERNS = [
    (r"\bis there (a|an|any) (tool|software|service|way|app|library|plugin)\b", 3.0, "is-there-a-tool"),
    (r"\bdoes anyone know (of )?(a |an |any )?(tool|software|service|way)\b", 3.0, "anyone-know-tool"),
    (r"\b(alternatives?|replacement) (to|for)\b", 2.0, "alternative-to"),
    (r"\b(manual(ly)?|by hand)\b", 1.5, "manual"),
    (r"\b(spreadsheets?|excel|google sheets?)\b", 1.5, "spreadsheet"),
    (r"\b(waste|wasting|wasted|spend|spending|spent)\s+(\w+\s+){0,2}(hours|days|time)\b", 2.5, "time-sink"),
    (r"\b(sick|tired|fed up) of\b", 2.0, "fed-up"),
    (r"\bwe (pay|paid|hired|outsourced?|contract(ed)?)\b", 3.0, "we-pay"),
    (r"\b(willing to pay|would pay|our budget|per (month|year)|\$\s?\d+)", 2.5, "money"),
    (r"\b(painful|tedious|annoying|frustrating|nightmare|clunky)\b", 1.0, "pain-word"),
    (r"\bwork-?arounds?\b", 2.0, "workaround"),
    (r"\bevery (day|week|month|sprint|release|deploy(ment)?)\b", 1.5, "recurring"),
    # noise: promo, students, hiring
    (r"\b(i built|i made|i created|we built|we launched|launching|check out my|show hn)\b", -3.0, "promo"),
    (r"\b(homework|for my class|my thesis|i'?m a student|hiring|we'?re hiring)\b", -3.0, "student-or-hiring"),
]
COMPILED = [(re.compile(p, re.I), w, label) for p, w, label in PATTERNS]


def score_text(text):
    score, hits = 0.0, []
    for rx, weight, label in COMPILED:
        if rx.search(text):
            score += weight
            hits.append(label)
    if len(text) < 80:
        score -= 1.0
    return score, hits


def run_scoring(con, rescore=False):
    where = "" if rescore else "WHERE kw_score IS NULL"
    rows = con.execute(f"SELECT uid, title, body FROM posts {where}").fetchall()
    updates = []
    for uid, title, body in rows:
        s, hits = score_text(f"{title or ''}\n{body or ''}")
        updates.append([s, ",".join(hits), uid])
    if updates:
        con.executemany("UPDATE posts SET kw_score = ?, kw_hits = ? WHERE uid = ?", updates)
    return len(updates)
