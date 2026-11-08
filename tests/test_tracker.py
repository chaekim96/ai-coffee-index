import json
from types import SimpleNamespace as NS

import pytest

from tracker import aggregate, build_site
from tracker.normalize import brand_key, domain
from tracker.providers import ask_claude


@pytest.mark.parametrize("a,b", [
    ("Blue Bottle Coffee", "Blue Bottle"),
    ("Blue Bottle Coffee (Hayes Valley)", "blue bottle"),
    ("Sightglass Coffee Roasters - SoMa", "Sightglass"),
    ("Philz Coffee, Berkeley", "Philz"),
    ("Café Réveille", "Reveille"),
    ("Abraço", "Abraco"),
    ("Joe & The Juice", "Joe and the Juice"),
    ("Devoción", "Devocion Coffee"),
    ("Coffee Project New York", "Coffee Project New York"),
])
def test_same_brand(a, b):
    assert brand_key(a) == brand_key(b)


def test_generic_words_never_empty_the_name():
    assert brand_key("Coffee") == "coffee"
    assert brand_key("The Coffee Shop") == "coffee shop"


def test_different_brands_stay_apart():
    assert brand_key("Blue Bottle") != brand_key("Blue Door Cafe")


def test_domain():
    assert domain("https://www.eater.com/maps/x?y=1") == "eater.com"
    assert domain("https://sf.eater.com/a") == "sf.eater.com"


def _row(provider, city, q, cafes, cited=()):
    return {"provider": provider, "city": city, "question": q, "error": "", "model_requested": "m", "model_served": "m",
            "cafes": [{"name": n, "neighborhood": "", "key": brand_key(n)} for n in cafes],
            "cited": [{"url": u, "title": "", "domain": domain(u)} for u in cited]}


ROWS = [
    _row("claude", "San Francisco", "q1", ["Sightglass Coffee", "Blue Bottle"], ["https://sf.eater.com/a", "https://sf.eater.com/b"]),
    _row("claude", "San Francisco", "q2", ["Sightglass", "Ritual Coffee Roasters"], ["https://www.yelp.com/x"]),
    _row("chatgpt", "San Francisco", "q1", ["Blue Bottle Coffee (Mint Plaza)", "Saint Frank"], ["https://sf.eater.com/a"]),
    _row("chatgpt", "San Francisco", "q2", ["Sightglass Coffee Roasters"]),
]
FAVS = [{"name": "Saint Frank Coffee", "city": "San Francisco", "key": brand_key("Saint Frank Coffee")},
        {"name": "Andytown", "city": "San Francisco", "key": brand_key("Andytown")}]


def test_summarize_counts_answers_not_mentions():
    s = aggregate.summarize(ROWS, FAVS)
    sf = s["cities"]["San Francisco"]
    top = sf["cafes"][0]
    assert top["name"] == "Sightglass Coffee" or top["key"] == "sightglass"
    assert top["by"] == {"claude": 2, "chatgpt": 1} and top["total"] == 3
    assert sf["answers"] == {"claude": 2, "chatgpt": 2}
    # Claude: sightglass, blue bottle, ritual. ChatGPT: blue bottle, saint frank, sightglass. Shared: 2 of 4.
    assert sf["agreement"] == 0.5
    # eater.com counted once per answer, not per link
    assert dict(sf["domains"]["claude"])["sf.eater.com"] == 1
    assert s["favorites"] == {"total": 2, "named": 1}
    saint = next(c for c in sf["cafes"] if c["key"] == "saint frank")
    assert saint["favorite"] is True


def test_changes_between_runs():
    prev = aggregate.summarize(ROWS[:2], [])
    cur = aggregate.summarize(ROWS, [])
    aggregate.add_changes(cur, prev)
    by = {c["key"]: c["change"] for c in cur["cities"]["San Francisco"]["cafes"]}
    assert by["sightglass"] == 1 and by["saint frank"] == "new" and by["ritual"] == 0


def test_build_site_end_to_end(tmp_path, monkeypatch):
    run = tmp_path / "data" / "runs" / "2026-11-09"
    run.mkdir(parents=True)
    (run / "answers.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    (tmp_path / "favorites.json").write_text(json.dumps([{"name": "Saint Frank Coffee", "city": "San Francisco, CA"}]))
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    monkeypatch.setattr(build_site, "SITE", tmp_path / "site")
    build_site.main()
    out = (tmp_path / "site" / "index.html").read_text()
    assert "Sightglass Coffee" in out and "★" in out and "November 9, 2026" in out
    assert "{" not in out.split("<body>")[1].split("<script>")[0]  # no unfilled template braces in the page body


def test_empty_site(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "ROOT", tmp_path)
    monkeypatch.setattr(build_site, "SITE", tmp_path / "site")
    build_site.main()
    assert "First run pending" in (tmp_path / "site" / "index.html").read_text()


class FakeClaude:
    """Stands in for the Anthropic client: first turn pauses, second answers with a citation."""
    def __init__(self):
        self.calls = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        usage = NS(input_tokens=100, output_tokens=50, server_tool_use=NS(web_search_requests=1))
        if len(self.calls) == 1:
            return NS(stop_reason="pause_turn", model="claude-opus-5-5", usage=usage, content=[
                NS(type="web_search_tool_result", content=[NS(url="https://sf.eater.com/maps/coffee", title="Eater")])])
        cite = NS(url="https://sf.eater.com/maps/coffee", title="Eater")
        return NS(stop_reason="end_turn", model="claude-opus-5-5", usage=usage, stop_details=None, content=[
            NS(type="text", text="Try Sightglass.", citations=[cite])])


def test_ask_claude_continues_paused_turn_and_keeps_citations():
    fake = FakeClaude()
    ans = ask_claude(fake, "best coffee in SF?")
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][-1]["role"] == "assistant"   # paused turn sent back
    assert fake.calls[0]["fallbacks"] == "default"
    assert ans.text == "Try Sightglass." and ans.cited[0]["domain"] == "sf.eater.com"
    assert ans.seen[0]["url"].endswith("/coffee") and ans.usage["web_searches"] == 2 and not ans.error
