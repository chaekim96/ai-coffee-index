"""One weekly run: ask every question to every assistant that has a key, extract the cafés,
and write data/runs/<date>/answers.jsonl.

    python -m tracker.run                     # all assistants with a key set
    python -m tracker.run --only claude --limit 2   # quick check: 2 questions per city

Re-running on the same date skips answers already saved, so a run that stops halfway can be finished.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .normalize import brand_key

ROOT = Path(__file__).resolve().parent.parent
PRICES = {  # USD per million tokens, for the cost line only
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
WEB_SEARCH_PER_1K = 10.00


def load_queries():
    q = json.loads((ROOT / "queries.json").read_text())
    return [(city, question) for city, qs in q["cities"].items() for question in qs]


def make_providers(only):
    providers = {}
    if os.environ.get("ANTHROPIC_API_KEY") and only in (None, "claude"):
        import anthropic
        from .providers import ask_claude
        c = anthropic.Anthropic(max_retries=4, timeout=600)
        providers["claude"] = lambda q: ask_claude(c, q)
    if os.environ.get("OPENAI_API_KEY") and only in (None, "chatgpt"):
        from .providers import OPENAI_MODEL, ask_openai
        if not OPENAI_MODEL:
            sys.exit("Set OPENAI_MODEL to the model ChatGPT uses (a repo variable in GitHub Actions).")
        import openai
        o = openai.OpenAI(max_retries=4, timeout=600)
        providers["chatgpt"] = lambda q: ask_openai(o, q)
    return providers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["claude", "chatgpt"])
    ap.add_argument("--limit", type=int, help="questions per city, for a quick check")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is needed: Claude Haiku pulls the café names out of every answer.")
    providers = make_providers(args.only)
    if not providers:
        sys.exit("No assistant to ask: set ANTHROPIC_API_KEY and/or OPENAI_API_KEY.")

    import anthropic
    from .extract import EXTRACT_MODEL, extract_cafes
    extractor = anthropic.Anthropic(max_retries=4)

    queries = load_queries()
    if args.limit:
        per_city = {}
        queries = [(c, q) for c, q in queries if per_city.setdefault(c, []).append(q) or len(per_city[c]) <= args.limit]

    # test runs (--limit) stay out of data/runs, so they never show up on the page or skew week-over-week changes
    out_dir = ROOT / "data" / ("test-runs" if args.limit else "runs") / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "answers.jsonl"
    done = set()
    if out_file.exists():
        for line in out_file.read_text().splitlines():
            r = json.loads(line)
            if not r["error"]:
                done.add((r["provider"], r["question"]))

    jobs = [(p, city, q) for city, q in queries for p in providers if (p, q) not in done]
    print(f"{len(jobs)} answers to get ({len(done)} already saved) from {', '.join(providers)}")

    def work(job):
        p, city, q = job
        ans = providers[p](q)
        row = {"city": city, "question": q, **ans.to_dict(), "cafes": [], "extract_usage": {}}
        if not ans.error:
            try:
                cafes, eu = extract_cafes(extractor, q, ans.text)
                row["cafes"] = [{**c, "key": brand_key(c["name"])} for c in cafes]
                row["extract_usage"] = eu
            except Exception as e:  # keep the answer; the next run on this date retries it
                row["error"] = f"extract failed: {e}"[:300]
        return row

    rows = [json.loads(l) for l in out_file.read_text().splitlines()] if out_file.exists() else []
    rows = [r for r in rows if not r["error"]]  # failed rows are retried
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(work, jobs):
            rows.append(row)
            flag = f"ERROR {row['error']}" if row["error"] else f"{len(row['cafes'])} cafés, {len(row['cited'])} cited"
            print(f"  {row['provider']:8} {row['question'][:60]:60} {flag}")
            out_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    # cost line (Claude only; OpenAI's prices aren't tracked here)
    cost = 0.0
    for r in rows:
        if r["provider"] == "claude":
            pin, pout = PRICES.get(r["model_requested"], (0, 0))
            u = r["usage"]
            cost += u.get("input_tokens", 0) / 1e6 * pin + u.get("output_tokens", 0) / 1e6 * pout
            cost += u.get("web_searches", 0) / 1000 * WEB_SEARCH_PER_1K
        pin, pout = PRICES.get(EXTRACT_MODEL, (0, 0))
        eu = r.get("extract_usage") or {}
        cost += eu.get("input_tokens", 0) / 1e6 * pin + eu.get("output_tokens", 0) / 1e6 * pout
    errors = sum(1 for r in rows if r["error"])
    print(f"Saved {len(rows)} answers to {out_file.relative_to(ROOT)} ({errors} with errors). "
          f"Claude + extraction cost about ${cost:.2f}.")
    if rows and errors == len(rows):
        sys.exit("Every answer failed; check the keys and model names above.")


if __name__ == "__main__":
    main()
