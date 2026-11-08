"""Build the public page (site/index.html + site/data.json) from every saved run.

    python -m tracker.build_site
"""
import html
import json
from pathlib import Path

from .aggregate import PROVIDER_LABEL, add_changes, load_favorites, load_runs, summarize

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
REPO = "https://github.com/chaekim96/ai-coffee-index"
PORTFOLIO = "https://chaekim.vercel.app"
SLUG = {"Berkeley/Oakland": "berkeley-oakland", "San Francisco": "san-francisco", "New York": "new-york"}

e = lambda s: html.escape(str(s), quote=True)


def pct(x):
    return f"{round(x * 100)}%"


def nice_date(iso):
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def bar(n, of, cls):
    w = 0 if not of else round(100 * n / of)
    return (f'<span class="bar {cls}" title="{n} of {of} answers"><i style="width:{w}%"></i></span>'
            f'<span class="num">{n}<small>/{of}</small></span>')


def change_cell(ch):
    if ch is None:
        return '<td class="chg"></td>'
    if ch == "new":
        return '<td class="chg"><span class="new">new</span></td>'
    if ch == 0:
        return '<td class="chg"><span class="flat">–</span></td>'
    return f'<td class="chg"><span class="{"up" if ch > 0 else "down"}">{"▲" if ch > 0 else "▼"} {abs(ch)}</span></td>'


def city_section(city, c, providers, show_change):
    slug = SLUG.get(city, city.lower().replace(" ", "-"))
    rows = []
    for i, x in enumerate(c["cafes"][:15], 1):
        star = '<span class="star" title="One of my favorites">★</span>' if x["favorite"] else ""
        cells = "".join(f'<td class="b">{bar(x["by"][p], c["answers"][p], p)}</td>' for p in providers)
        rows.append(f'<tr><td class="rk">{i}</td><td class="nm">{e(x["name"])}{star}</td>{cells}'
                    f'{change_cell(x.get("change")) if show_change else ""}</tr>')
    more = len(c["cafes"]) - 15
    head = "".join(f'<th class="b"><span class="dot {p}"></span>{PROVIDER_LABEL.get(p, p)}</th>' for p in providers)

    favs = c["favorites"]
    fav_html = ""
    if favs:
        named = [f for f in favs if sum(f["by"].values())]
        missed = [f for f in favs if not sum(f["by"].values())]
        items = "".join(
            f'<li class="{"hit" if sum(f["by"].values()) else "miss"}"><span>{e(f["name"])}</span>'
            f'<small>{" · ".join(f"{PROVIDER_LABEL.get(p, p)} {f["by"][p]}" for p in providers if f["by"][p]) or "not named"}</small></li>'
            for f in named + missed)
        fav_html = (f'<div class="favs"><h3>My favorites here: {len(named)} of {len(favs)} named</h3>'
                    f'<ul>{items}</ul></div>')

    src = "".join(
        f'<div class="src"><h4><span class="dot {p}"></span>{PROVIDER_LABEL.get(p, p)} cites</h4><ol>'
        + "".join(f'<li><span>{e(d)}</span><b>{n}</b></li>' for d, n in c["domains"][p][:6])
        + ("" if c["domains"][p] else "<li><span>No citations</span></li>") + "</ol></div>"
        for p in providers)

    agree = (f'<p class="agree">Of the cafés either assistant named, <b>{pct(c["agreement"])}</b> were named by both '
             f'({" · ".join(f"{PROVIDER_LABEL.get(p, p)} named {c["distinct"][p]}" for p in providers)}).</p>'
             if c["agreement"] is not None else "")
    return f"""
    <section class="city" id="{slug}" aria-labelledby="{slug}-h">
      <h2 id="{slug}-h">{e(city)}</h2>
      {agree}
      <div class="tablewrap"><table>
        <thead><tr><th class="rk">#</th><th class="nm">Café</th>{head}{'<th class="chg">vs last week</th>' if show_change else ""}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table></div>
      {f'<p class="more">Plus {more} more cafés named once or twice.</p>' if more > 0 else ""}
      <div class="side">{fav_html}<div class="srcs">{src}</div></div>
    </section>"""


def page(summary, run_date, n_runs):
    if summary is None:
        body = '<section class="empty"><h2>First run pending</h2><p>The first weekly run hasn\'t happened yet. Check back soon.</p></section>'
        stats, tabs, meta = "", "", ""
    else:
        providers = summary["providers"]
        f = summary["favorites"]
        tiles = []
        if f["total"]:
            tiles.append(f'<div class="tile"><b>{f["named"]}<small> of {f["total"]}</small></b><span>of my favorite cafés got named by at least one assistant</span></div>')
        if summary["agreement"] is not None:
            tiles.append(f'<div class="tile"><b>{pct(summary["agreement"])}</b><span>overlap between ChatGPT\'s and Claude\'s picks, averaged across cities</span></div>')
        if summary["top_domains"]:
            d, n = summary["top_domains"][0]
            tiles.append(f'<div class="tile"><b class="dom">{e(d)}</b><span>most-cited source, in {n} of {summary["answers"]} answers</span></div>')
        stats = f'<div class="tiles">{"".join(tiles)}</div>'
        tabs = '<nav class="tabs" aria-label="Cities">' + "".join(
            f'<a href="#{SLUG.get(c, c)}">{e(c)}</a>' for c in summary["cities"]) + "</nav>"
        body = "".join(city_section(c, d, providers, n_runs > 1) for c, d in summary["cities"].items())
        meta = (f'<p class="meta">Run of {nice_date(run_date)} · {summary["questions"]} questions · {summary["answers"]} answers · '
                f'models: {", ".join(e(m) for m in summary["models"])}</p>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Coffee Index</title>
<meta name="description" content="Every week I ask ChatGPT and Claude where to get coffee in Berkeley, San Francisco and New York, and track which cafés they name and which sources they trust.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Poppins:wght@400;500;600&display=swap">
<script>try{{var t=localStorage.getItem('aci-theme');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<style>
/* Layout: one column of cities, each a ranked table with favorites and sources beside it. Paper, espresso ink, crema accent. */
:root {{
  --bg: #fbf8f3; --card: #ffffff; --ink: #2a1d15; --ink-2: #6f6158; --line: rgba(42,29,21,.12); --fill: rgba(42,29,21,.05);
  --crema: #c27a3a; --claude: #d9774b; --chatgpt: #2f7d6d; --up: #2f7d4f; --down: #b8473a; --star: #d4a017;
  --display: "Fraunces", Georgia, "Times New Roman", serif; --body: "Poppins", system-ui, -apple-system, "Segoe UI", sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #16110e; --card: #201914; --ink: #f3ebe3; --ink-2: #b4a69b; --line: rgba(243,235,227,.12); --fill: rgba(243,235,227,.06);
  --crema: #e2a065; --claude: #ee9a72; --chatgpt: #5fb8a5; --up: #6cc08d; --down: #ec7f71; --star: #f0c14b; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #16110e; --card: #201914; --ink: #f3ebe3; --ink-2: #b4a69b; --line: rgba(243,235,227,.12); --fill: rgba(243,235,227,.06);
  --crema: #e2a065; --claude: #ee9a72; --chatgpt: #5fb8a5; --up: #6cc08d; --down: #ec7f71; --star: #f0c14b; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 400 15px/1.6 var(--body); }}
a {{ color: inherit; }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding-block: 48px 64px; padding-left: max(20px, env(safe-area-inset-left, 0px)); padding-right: max(20px, env(safe-area-inset-right, 0px)); }}
header {{ display: grid; gap: 10px; max-width: 720px; }}
.eyebrow {{ font-size: 12px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--crema); margin: 0; }}
h1 {{ font: 600 clamp(34px, 5vw, 52px)/1.05 var(--display); letter-spacing: -.02em; margin: 0; text-wrap: balance; }}
.lede {{ color: var(--ink-2); font-size: 17px; margin: 0; max-width: 62ch; }}
.meta {{ color: var(--ink-2); font-size: 13px; margin: 4px 0 0; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 32px 0 8px; }}
.tile {{ background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; display: grid; gap: 4px; }}
.tile b {{ font: 600 34px/1.1 var(--display); }} .tile b small {{ font-size: 18px; color: var(--ink-2); font-weight: 500; }}
.tile b.dom {{ font-size: 22px; overflow-wrap: anywhere; }}
.tile span {{ color: var(--ink-2); font-size: 13px; }}
.tabs {{ position: sticky; top: 0; z-index: 2; display: flex; gap: 6px; flex-wrap: wrap; padding: 12px 0; margin-top: 24px; background: var(--bg); border-bottom: 1px solid var(--line); }}
.tabs a {{ text-decoration: none; padding: 6px 14px; border-radius: 999px; font-size: 14px; color: var(--ink-2); background: var(--fill); }}
.tabs a:hover, .tabs a:focus-visible {{ color: var(--ink); }}
.city {{ padding-top: 40px; scroll-margin-top: 60px; display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 8px 32px; align-items: start; }}
.city h2 {{ grid-column: 1 / -1; font: 600 30px/1.2 var(--display); margin: 0; }}
.agree {{ grid-column: 1 / -1; color: var(--ink-2); margin: 0 0 8px; }} .agree b {{ color: var(--ink); }}
.tablewrap {{ overflow-x: auto; background: var(--card); border: 1px solid var(--line); border-radius: 16px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }}
th {{ text-align: left; font-weight: 500; font-size: 12px; color: var(--ink-2); padding: 12px 14px; border-bottom: 1px solid var(--line); white-space: nowrap; }}
td {{ padding: 9px 14px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
tr:last-child td {{ border-bottom: 0; }}
.rk {{ width: 28px; color: var(--ink-2); }} .nm {{ font-weight: 500; min-width: 150px; }}
td.b {{ white-space: nowrap; width: 150px; }}
.bar {{ display: inline-block; width: 72px; height: 8px; border-radius: 99px; background: var(--fill); vertical-align: middle; margin-right: 8px; overflow: hidden; }}
.bar i {{ display: block; height: 100%; border-radius: 99px; }}
.bar.claude i {{ background: var(--claude); }} .bar.chatgpt i {{ background: var(--chatgpt); }}
.num small {{ color: var(--ink-2); }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }}
.dot.claude {{ background: var(--claude); }} .dot.chatgpt {{ background: var(--chatgpt); }}
.star {{ color: var(--star); margin-left: 6px; }}
.chg {{ width: 90px; font-size: 13px; }} .up {{ color: var(--up); }} .down {{ color: var(--down); }} .flat {{ color: var(--ink-2); }}
.new {{ font-size: 11px; font-weight: 600; color: var(--crema); text-transform: uppercase; letter-spacing: .06em; }}
.more {{ color: var(--ink-2); font-size: 13px; margin: 8px 0 0; }}
.side {{ display: grid; gap: 16px; }}
.favs, .src {{ background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 16px 18px; }}
.favs h3, .src h4 {{ margin: 0 0 10px; font-size: 14px; font-weight: 600; }}
.favs ul, .src ol {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }}
.favs li {{ display: flex; justify-content: space-between; gap: 10px; font-size: 14px; }}
.favs li small {{ color: var(--ink-2); white-space: nowrap; }}
.favs li.hit span::before {{ content: "★ "; color: var(--star); }}
.favs li.miss span {{ color: var(--ink-2); }} .favs li.miss span::before {{ content: "☆ "; }}
.srcs {{ display: grid; gap: 16px; }}
.src li {{ display: flex; justify-content: space-between; gap: 10px; font-size: 13px; }}
.src li span {{ overflow-wrap: anywhere; }} .src li b {{ font-weight: 500; color: var(--ink-2); }}
.how {{ margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--line); max-width: 720px; color: var(--ink-2); }}
.how h2 {{ font: 600 22px/1.2 var(--display); color: var(--ink); margin: 0 0 8px; }}
.how li {{ margin-bottom: 6px; }}
footer {{ margin-top: 40px; font-size: 13px; color: var(--ink-2); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
.theme {{ border: 1px solid var(--line); background: var(--card); color: var(--ink); border-radius: 999px; padding: 4px 12px; font: inherit; font-size: 13px; cursor: pointer; }}
.empty {{ margin-top: 40px; padding: 32px; border: 1px dashed var(--line); border-radius: 16px; }}
:focus-visible {{ outline: 3px solid var(--crema); outline-offset: 2px; border-radius: 6px; }}
@media (max-width: 820px) {{ .city {{ grid-template-columns: minmax(0, 1fr); }} td.b {{ width: auto; }} .bar {{ width: 44px; }} }}
@media (max-width: 560px) {{ .bar {{ display: none; }} th, td {{ padding: 9px 10px; }} .nm {{ min-width: 0; }} .chg {{ width: auto; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <p class="eyebrow">AI Coffee Index</p>
    <h1>Where AI sends you for coffee</h1>
    <p class="lede">Every week I ask ChatGPT and Claude the coffee questions people actually type, about Berkeley, San Francisco and New York, with web search on. Then I track which cafés they name, how often they agree, and which websites they trust. ★ marks cafés from my own saved list.</p>
    {meta}
  </header>
  {stats}
  {tabs}
  {body}
  <section class="how">
    <h2>How this works</h2>
    <ul>
      <li>Each city gets the same 10 questions every week, asked fresh with no chat history, like a new user would.</li>
      <li>A bar shows how many of a city's 10 answers named that café. Branches of one café count once.</li>
      <li>A small Claude model reads every answer and lists the cafés it recommends, so formatting differences don't matter.</li>
      <li>"Cites" counts answers that link to a site, not individual links.</li>
      <li>Answers vary from run to run, so a single week is one sample. Trends over several weeks say more.</li>
    </ul>
  </section>
  <footer>
    <span>By <a href="{PORTFOLIO}">Chae Kim</a> · <a href="{REPO}">Code and data on GitHub</a></span>
    <button class="theme" type="button" id="theme">Toggle dark mode</button>
  </footer>
</div>
<script>
document.getElementById('theme').addEventListener('click', function () {{
  var r = document.documentElement, dark = r.getAttribute('data-theme') ? r.getAttribute('data-theme') === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  r.setAttribute('data-theme', dark ? 'light' : 'dark');
  try {{ localStorage.setItem('aci-theme', dark ? 'light' : 'dark'); }} catch (e) {{}}
}});
</script>
</body>
</html>
"""


def main():
    runs = load_runs(ROOT)
    favorites = load_favorites(ROOT)
    SITE.mkdir(exist_ok=True)
    if not runs:
        (SITE / "index.html").write_text(page(None, None, 0))
        print("No runs yet: wrote the empty page.")
        return
    summaries = [(d, summarize(rows, favorites)) for d, rows in runs]
    prev = summaries[-2][1] if len(summaries) > 1 else None
    run_date, cur = summaries[-1]
    add_changes(cur, prev)
    (SITE / "index.html").write_text(page(cur, run_date, len(runs)))
    history = [{"date": d, "favorites": s["favorites"], "agreement": s["agreement"],
                "top": {c: [x["name"] for x in v["cafes"][:5]] for c, v in s["cities"].items()}} for d, s in summaries]
    (SITE / "data.json").write_text(json.dumps({"date": run_date, "latest": cur, "history": history}, ensure_ascii=False, indent=1))
    print(f"Wrote site/index.html from {len(runs)} run(s); latest {run_date}.")


if __name__ == "__main__":
    main()
