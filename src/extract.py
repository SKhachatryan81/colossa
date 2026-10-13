"""LLM extraction: turn a promising post into structured pain-signal fields.

Needs ANTHROPIC_API_KEY. Model can be overridden with PS_MODEL.
"""
import json
import os
import re
from datetime import datetime, timezone

MODEL = os.environ.get("PS_MODEL", "claude-haiku-5-5")

SYSTEM = """You analyse online posts to find real, recurring business or professional pain points.
Given one post, decide whether the author (or a commenter) describes a genuine problem that a
product could solve. Ignore promotion, hypotheticals, students, job ads, and pure venting.

Reply with ONLY a JSON object with these keys:
- is_pain: boolean, true only for a real, concrete problem
- who: short description of the person's role/industry (e.g. "platform engineer at a mid-size company"), or ""
- problem: one sentence describing the problem, or ""
- workaround: what they do today (manual process, spreadsheet, tool, hired help), or ""
- cost_signal: any mention of hours, money, or budget, quoted briefly, or ""
- frequency: one of "daily", "weekly", "monthly", "occasional", "unknown"
- pays: boolean, true only if they pay for, or say they would pay for, a solution
- confidence: number between 0 and 1
"""


def parse_json(text):
    """Be forgiving: strip code fences and grab the outermost {...}."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def select_candidates(con, limit, min_score):
    return con.execute(
        """
        SELECT p.uid, p.source, p.container, p.title, p.body
        FROM posts p LEFT JOIN extractions e ON e.uid = p.uid
        WHERE e.uid IS NULL AND p.kw_score >= ?
        ORDER BY p.kw_score DESC
        LIMIT ?
        """,
        [min_score, limit],
    ).fetchall()


def run_extraction(con, limit=50, min_score=3.0, dry_run=False):
    candidates = select_candidates(con, limit, min_score)
    chars = sum(len(c[3] or "") + min(len(c[4] or ""), 3000) for c in candidates)
    print(f"{len(candidates)} posts selected (~{chars // 4:,} input tokens, plus prompt overhead)")
    if dry_run or not candidates:
        return 0

    try:
        import anthropic
    except ImportError:
        raise SystemExit("Install the SDK first: pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first.")
    client = anthropic.Anthropic()

    done = 0
    for uid, source, container, title, body in candidates:
        content = f"Source: {source} / {container}\nTitle: {title}\n\n{(body or '')[:3000]}"
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
            )
            d = parse_json(resp.content[0].text)
            con.execute(
                "INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    uid,
                    bool(d.get("is_pain")),
                    d.get("who", ""),
                    d.get("problem", ""),
                    d.get("workaround", ""),
                    d.get("cost_signal", ""),
                    d.get("frequency", "unknown"),
                    bool(d.get("pays")),
                    float(d.get("confidence", 0)),
                    MODEL,
                    datetime.now(timezone.utc).replace(tzinfo=None),
                ],
            )
            done += 1
            print(f"  [{done}/{len(candidates)}] {uid}: pain={d.get('is_pain')}")
        except Exception as exc:  # keep going; one bad reply shouldn't stop the batch
            print(f"  skipped {uid}: {exc}")
    return done
