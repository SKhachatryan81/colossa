"""Reports. Works without the LLM step via --no-llm (keyword scores only)."""
import textwrap


def print_stats(con):
    print("\n== Data ==")
    for source, n in con.execute("SELECT source, count(*) FROM posts GROUP BY 1 ORDER BY 2 DESC").fetchall():
        print(f"  {source:<8} {n:>7,} posts")
    scored = con.execute("SELECT count(*) FROM posts WHERE kw_score >= 3").fetchone()[0]
    extracted = con.execute("SELECT count(*) FROM extractions").fetchone()[0]
    pains = con.execute("SELECT count(*) FROM extractions WHERE is_pain").fetchone()[0]
    print(f"  keyword candidates (score >= 3): {scored:,}")
    print(f"  LLM-extracted: {extracted:,}  (real pain: {pains:,})")


def print_keyword_top(con, top=20):
    print(f"\n== Top {top} posts by keyword score ==")
    rows = con.execute(
        """
        SELECT kw_score, source, container, title, url, kw_hits
        FROM posts WHERE kw_score IS NOT NULL
        ORDER BY kw_score DESC, created_at DESC LIMIT ?
        """,
        [top],
    ).fetchall()
    for score, source, container, title, url, hits in rows:
        print(f"\n[{score:.1f}] {source}/{container}\n  {textwrap.shorten(title or '(no title)', 100)}\n  {url}\n  hits: {hits}")


def print_llm_top(con, top=20, min_conf=0.6):
    print(f"\n== Top {top} extracted pain signals ==")
    rows = con.execute(
        """
        SELECT e.who, e.problem, e.workaround, e.cost_signal, e.frequency, e.pays,
               e.confidence, p.source, p.container, p.url
        FROM extractions e JOIN posts p ON p.uid = e.uid
        WHERE e.is_pain AND e.confidence >= ?
        ORDER BY e.pays DESC, e.confidence DESC, p.kw_score DESC
        LIMIT ?
        """,
        [min_conf, top],
    ).fetchall()
    if not rows:
        print("  nothing yet - run `extract` first (or lower --min-conf)")
    for who, problem, workaround, cost, freq, pays, conf, source, container, url in rows:
        print(f"\n* {problem}")
        print(f"  who: {who} | frequency: {freq} | pays: {pays} | confidence: {conf:.2f}")
        print(f"  workaround: {workaround or '-'}")
        print(f"  cost signal: {cost or '-'}")
        print(f"  {source}/{container}  {url}")


def export_csv(con, path):
    con.execute(
        f"""
        COPY (
            SELECT p.source, p.container, p.title, p.url, p.created_at, p.kw_score, p.kw_hits,
                   e.is_pain, e.who, e.problem, e.workaround, e.cost_signal, e.frequency, e.pays, e.confidence
            FROM posts p LEFT JOIN extractions e ON e.uid = p.uid
            WHERE p.kw_score >= 3
            ORDER BY p.kw_score DESC
        ) TO '{path}' (HEADER, DELIMITER ',')
        """
    )
    print(f"\nExported to {path}")
