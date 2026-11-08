"""Ask each assistant a question the way a person would, with web search on, and keep what it
said, which pages it cited, and which pages it looked at.

Each provider returns an Answer. A failure is recorded on the Answer, never raised, so one bad
call doesn't stop a weekly run.
"""
import os
from dataclasses import dataclass, field, asdict

from .normalize import domain

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL") or ""   # set to the model ChatGPT uses, e.g. in a repo variable
WEB_SEARCH_MAX_USES = 5


@dataclass
class Answer:
    provider: str
    model_requested: str
    model_served: str = ""
    text: str = ""
    cited: list = field(default_factory=list)    # [{url, title, domain}] pages the answer cites
    seen: list = field(default_factory=list)     # [{url, title, domain}] pages the search returned
    usage: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self):
        return asdict(self)


def _page(url, title):
    return {"url": url, "title": title or "", "domain": domain(url)}


def _dedupe(pages):
    out, seen = [], set()
    for p in pages:
        if p["url"] and p["url"] not in seen:
            seen.add(p["url"])
            out.append(p)
    return out


# ---------------------------------------------------------------- Claude
def ask_claude(client, question: str) -> Answer:
    import anthropic

    ans = Answer("claude", CLAUDE_MODEL)
    messages = [{"role": "user", "content": question}]
    blocks, usage = [], {"input_tokens": 0, "output_tokens": 0, "web_searches": 0}
    try:
        for _ in range(4):  # a long search turn can pause; send it back to let the server continue
            r = client.beta.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",          # if Claude declines, Anthropic's recommended model answers instead
                output_config={"effort": "medium"},
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}],
                messages=messages,
            )
            blocks += r.content
            usage["input_tokens"] += r.usage.input_tokens or 0
            usage["output_tokens"] += r.usage.output_tokens or 0
            stu = getattr(r.usage, "server_tool_use", None)
            usage["web_searches"] += getattr(stu, "web_search_requests", 0) or 0
            ans.model_served = r.model
            if r.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": r.content})
        if r.stop_reason == "refusal":
            ans.error = f"refused ({getattr(r.stop_details, 'category', None)})"
    except anthropic.APIError as e:  # SDK already retried rate limits and server errors
        ans.error = f"{type(e).__name__}: {e}"[:300]
        return ans

    texts, cited, seen = [], [], []
    for b in blocks:
        if b.type == "text":
            texts.append(b.text)
            for c in b.citations or []:
                if getattr(c, "url", None):
                    cited.append(_page(c.url, getattr(c, "title", "")))
        elif b.type == "web_search_tool_result" and isinstance(b.content, list):  # an error is an object, not a list
            for res in b.content:
                if getattr(res, "url", None):
                    seen.append(_page(res.url, getattr(res, "title", "")))
    ans.text = "".join(texts).strip()
    ans.cited, ans.seen, ans.usage = _dedupe(cited), _dedupe(seen), usage
    return ans


# ---------------------------------------------------------------- ChatGPT (OpenAI)
def ask_openai(client, question: str) -> Answer:
    import openai

    ans = Answer("chatgpt", OPENAI_MODEL)
    try:
        r = client.responses.create(
            model=OPENAI_MODEL,
            input=question,
            tools=[{"type": "web_search"}],
            include=["web_search_call.action.sources"],
        )
    except openai.APIError as e:
        ans.error = f"{type(e).__name__}: {e}"[:300]
        return ans

    cited, seen = [], []
    for item in r.output or []:
        if item.type == "message":
            for part in item.content or []:
                for a in getattr(part, "annotations", None) or []:
                    if getattr(a, "type", "") == "url_citation":
                        cited.append(_page(a.url, getattr(a, "title", "")))
        elif item.type == "web_search_call":
            action = getattr(item, "action", None)
            for s in getattr(action, "sources", None) or []:
                if getattr(s, "url", None):
                    seen.append(_page(s.url, getattr(s, "title", "")))
    ans.model_served = r.model
    ans.text = (r.output_text or "").strip()
    ans.cited, ans.seen = _dedupe(cited), _dedupe(seen)
    u = r.usage
    ans.usage = {"input_tokens": getattr(u, "input_tokens", 0), "output_tokens": getattr(u, "output_tokens", 0)}
    return ans
