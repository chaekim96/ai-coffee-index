# AI Coffee Index

Every week, this asks ChatGPT and Claude the coffee questions people actually type (for Berkeley/Oakland, San Francisco and New York) with web search on. It records which cafés they name, how often they agree, which websites they cite, and how many of my own favorite cafés they know about.

The page is rebuilt after every run and published with GitHub Pages.

## How a run works

1. `queries.json` holds 10 questions per city. Each is asked fresh, with no chat history.
2. `tracker/providers.py` asks each assistant with its web search tool on and saves the answer, the pages it cited, and the pages its search returned.
3. `tracker/extract.py` has Claude Haiku list the cafés each answer recommends (structured output), so formatting differences between assistants don't matter.
4. `tracker/normalize.py` merges name variants ("Blue Bottle Coffee (Mint Plaza)" = "Blue Bottle").
5. `tracker/aggregate.py` and `tracker/build_site.py` turn every saved run into `site/index.html` and `site/data.json`.

Raw answers are kept in `data/runs/<date>/answers.jsonl`, so every number on the page can be traced to the text it came from.

## Setup (once)

1. **Secrets** (Settings → Secrets and variables → Actions → Secrets): `ANTHROPIC_API_KEY` (required, also used for extraction) and `OPENAI_API_KEY`.
2. **Variable** (same page → Variables): `OPENAI_MODEL`, the model ChatGPT uses.
3. **Pages** (Settings → Pages): set Source to **GitHub Actions**.
4. **Favorites**: `favorites.json` is a list of `{"name", "city"}` from my Google Maps Favorites (cafés only).

## Running

- Weekly: Mondays, automatically (`.github/workflows/weekly.yml`).
- By hand: Actions → Weekly run → Run workflow. Set **limit** to `1` for a cheap test (saved under `data/test-runs/`, not shown on the page), or tick **build_only** to rebuild the page without API calls.
- Locally:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
ANTHROPIC_API_KEY=... OPENAI_API_KEY=... OPENAI_MODEL=... .venv/bin/python -m tracker.run --limit 1
.venv/bin/python -m tracker.build_site   # writes site/index.html
```

`CLAUDE_MODEL` (default `claude-opus-5-5`) and `EXTRACT_MODEL` (default `claude-haiku-5-5`) can be overridden the same way.

## Notes

- Claude calls use Anthropic's server-side fallback (`fallbacks: "default"`): if Claude declines a question, a recommended fallback model answers instead, and the served model is saved with the answer.
- Changing a question breaks week-over-week comparison for that city, so edit `queries.json` sparingly.
- Answers vary run to run. One week is one sample; the trend is the point.
