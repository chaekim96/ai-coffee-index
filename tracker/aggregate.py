"""Turn saved answers into the numbers the page shows. Pure functions, no API calls."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .normalize import brand_key

PROVIDER_LABEL = {"claude": "Claude", "chatgpt": "ChatGPT"}
# Cities in Chae's places data -> city keys in queries.json
FAVORITE_CITY = {
    "Berkeley/Oakland, CA": "Berkeley/Oakland",
    "San Francisco, CA": "San Francisco",
    "New York, NY": "New York",
}


def load_runs(root: Path) -> list[tuple[str, list]]:
    runs = []
    for d in sorted((root / "data" / "runs").glob("*/answers.jsonl")):
        rows = [json.loads(l) for l in d.read_text().splitlines() if l.strip()]
        rows = [r for r in rows if not r.get("error")]
        if rows:
            runs.append((d.parent.name, rows))
    return runs


def load_favorites(root: Path) -> list[dict]:
    f = root / "favorites.json"
    if not f.exists():
        return []
    out = []
    for p in json.loads(f.read_text()):
        city = FAVORITE_CITY.get(p.get("city"), p.get("city"))
        if p.get("name"):
            out.append({"name": p["name"], "city": city, "key": brand_key(p["name"]), "url": p.get("url") or ""})
    return out


def _display(names: list[str]) -> str:
    clean = [re.sub(r"\s*\(.*?\)\s*", " ", n).strip() for n in names]
    return Counter(clean).most_common(1)[0][0]


def summarize(rows: list[dict], favorites: list[dict]) -> dict:
    providers = sorted({r["provider"] for r in rows}, key=lambda p: list(PROVIDER_LABEL).index(p) if p in PROVIDER_LABEL else 9)
    fav_keys = {(f["city"], f["key"]) for f in favorites}
    cities = {}
    for city in dict.fromkeys(r["city"] for r in rows):
        crow = [r for r in rows if r["city"] == city]
        answers = Counter(r["provider"] for r in crow)
        by = defaultdict(Counter)      # key -> provider -> answers naming it
        first = defaultdict(Counter)   # key -> provider -> answers naming it first
        names = defaultdict(list)
        for r in crow:
            keys_here = []
            for c in r["cafes"]:
                if c["key"] and c["key"] not in keys_here:
                    keys_here.append(c["key"])
                    names[c["key"]].append(c["name"])
            for i, k in enumerate(keys_here):
                by[k][r["provider"]] += 1
                if i == 0:
                    first[k][r["provider"]] += 1
        cafes = [{
            "key": k,
            "name": _display(names[k]),
            "by": {p: by[k][p] for p in providers},
            "first": sum(first[k].values()),
            "total": sum(by[k].values()),
            "favorite": (city, k) in fav_keys,
        } for k in by]
        cafes.sort(key=lambda c: (-c["total"], -c["first"], c["name"].lower()))

        sets = {p: {k for k in by if by[k][p]} for p in providers}
        agreement = None
        if len(providers) == 2 and all(sets.values()):
            a, b = sets.values()
            agreement = round(len(a & b) / len(a | b), 3)

        domains = {p: Counter() for p in providers}
        for r in crow:
            for d in {c["domain"] for c in r["cited"] if c["domain"]}:
                domains[r["provider"]][d] += 1

        favs = [f for f in favorites if f["city"] == city]
        cities[city] = {
            "answers": {p: answers[p] for p in providers},
            "cafes": cafes,
            "distinct": {p: len(sets[p]) for p in providers},
            "agreement": agreement,
            "domains": {p: domains[p].most_common(8) for p in providers},
            "favorites": [{**f, "by": {p: by[f["key"]][p] for p in providers}} for f in favs],
        }

    all_domains = Counter()
    for r in rows:
        for d in {c["domain"] for c in r["cited"] if c["domain"]}:
            all_domains[d] += 1
    fav_total = sum(len(c["favorites"]) for c in cities.values())
    fav_named = sum(1 for c in cities.values() for f in c["favorites"] if sum(f["by"].values()))
    agreements = [c["agreement"] for c in cities.values() if c["agreement"] is not None]
    return {
        "providers": providers,
        "answers": len(rows),
        "questions": len({r["question"] for r in rows}),
        "cities": cities,
        "top_domains": all_domains.most_common(10),
        "cited_share": round(sum(1 for r in rows if r["cited"]) / len(rows), 3) if rows else 0,
        "favorites": {"total": fav_total, "named": fav_named},
        "agreement": round(sum(agreements) / len(agreements), 3) if agreements else None,
        "models": sorted({r.get("model_served") or r["model_requested"] for r in rows}),
    }


def add_changes(cur: dict, prev: dict | None) -> None:
    """Mark each café with how its mention count moved since the previous run."""
    for city, c in cur["cities"].items():
        before = {x["key"]: x["total"] for x in (prev or {}).get("cities", {}).get(city, {}).get("cafes", [])}
        for x in c["cafes"]:
            x["change"] = None if prev is None else (x["total"] - before[x["key"]] if x["key"] in before else "new")
