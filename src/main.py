"""painsignals CLI.

  python main.py collect --sources hn,github --days 7
  python main.py score
  python main.py extract --dry-run
  python main.py extract --limit 50
  python main.py report --no-llm
"""
import argparse

import collectors
import db
import extract
import report
import score


def cmd_collect(args, con):
    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    runners = {
        "hn": lambda: collectors.collect_hn(days=args.days),
        "github": lambda: collectors.collect_github(days=args.days),
        "reddit": lambda: collectors.collect_reddit(),
    }
    for name in wanted:
        if name not in runners:
            print(f"unknown source '{name}' (choose from: {', '.join(runners)})")
            continue
        print(f"Collecting {name}...")
        rows = runners[name]()
        new = db.upsert_posts(con, rows)
        print(f"  {name}: fetched {len(rows)}, {new} new")
    n = score.run_scoring(con)
    print(f"Scored {n} new posts.")


def cmd_score(args, con):
    n = score.run_scoring(con, rescore=args.rescore)
    print(f"Scored {n} posts.")


def cmd_extract(args, con):
    n = extract.run_extraction(con, limit=args.limit, min_score=args.min_score, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Extracted {n} posts.")


def cmd_report(args, con):
    report.print_stats(con)
    if args.no_llm:
        report.print_keyword_top(con, args.top)
    else:
        report.print_llm_top(con, args.top, args.min_conf)
    if args.csv:
        report.export_csv(con, args.csv)


def main():
    p = argparse.ArgumentParser(description="Local pain-signal miner")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="fetch posts and keyword-score them")
    c.add_argument("--sources", default="hn,github", help="comma list: hn,github,reddit")
    c.add_argument("--days", type=int, default=7, help="look-back window")
    c.set_defaults(fn=cmd_collect)

    s = sub.add_parser("score", help="(re)run keyword scoring")
    s.add_argument("--rescore", action="store_true", help="rescore everything, e.g. after editing patterns")
    s.set_defaults(fn=cmd_score)

    e = sub.add_parser("extract", help="LLM extraction on top-scoring posts")
    e.add_argument("--limit", type=int, default=50)
    e.add_argument("--min-score", type=float, default=3.0)
    e.add_argument("--dry-run", action="store_true", help="only show how many posts would be sent")
    e.set_defaults(fn=cmd_extract)

    r = sub.add_parser("report", help="show results")
    r.add_argument("--top", type=int, default=20)
    r.add_argument("--no-llm", action="store_true", help="rank by keyword score only")
    r.add_argument("--min-conf", type=float, default=0.6)
    r.add_argument("--csv", help="also export candidates to this CSV path")
    r.set_defaults(fn=cmd_report)

    args = p.parse_args()
    con = db.connect()
    args.fn(args, con)


if __name__ == "__main__":
    main()
