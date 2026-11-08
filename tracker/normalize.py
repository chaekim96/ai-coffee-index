"""Turn café names and URLs into stable keys, so "Blue Bottle Coffee (Hayes Valley)",
"Blue Bottle" and "blue bottle coffee co." all count as the same place."""
import re
import unicodedata
from urllib.parse import urlparse

# Generic words that don't identify a café. Removed from the end (and "cafe" from the start),
# never when they are the whole name.
_TRAILING = [
    "coffee roasting company", "coffee roasting co", "coffee roasters", "coffee roastery", "coffee company",
    "coffee co", "coffee bar", "coffee shop", "coffee house", "coffeehouse", "espresso bar", "roasting company",
    "roasting co", "roasters", "roastery", "coffee", "cafe", "co", "company", "inc", "llc",
]
_LEADING = ["the ", "cafe ", "caffe "]


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = s.replace("&", " and ").replace("’", "'")
    s = re.sub(r"\(.*?\)", " ", s)          # "(Hayes Valley)"
    s = re.split(r"\s[-–—|]\s|,|:", s)[0]   # "Sightglass - SoMa", "Philz, Berkeley"
    s = re.sub(r"'s\b", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def brand_key(name: str) -> str:
    """A key for grouping: one key per café brand within a city (branches merge)."""
    s = _plain(name)
    changed = True
    while changed:
        changed = False
        for lead in _LEADING:
            if s.startswith(lead) and len(s) > len(lead):
                s, changed = s[len(lead):], True
        for word in _TRAILING:
            if s.endswith(" " + word):
                s, changed = s[: -len(word) - 1].strip(), True
    return s


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host
