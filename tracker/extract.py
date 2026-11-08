"""Pull the recommended cafés out of an answer with a small, cheap model and structured output.
Free text varies a lot between assistants; asking a model to list the names is more reliable
than parsing bullets and bold text."""
import json
import os

EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL") or "claude-haiku-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "cafes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "neighborhood": {"type": "string"},
                },
                "required": ["name", "neighborhood"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cafes"],
    "additionalProperties": False,
}

PROMPT = """Below is an AI assistant's answer to someone who asked: "{question}"

List every coffee shop or café the answer recommends, in the order it first mentions them.
- name: the shop's name as the answer writes it, without the neighborhood, street or city.
- neighborhood: the branch, neighborhood or street the answer gives for it, or "" if none.
Leave out places the answer only warns against or mentions in passing without recommending,
and leave out anything that isn't a place to get coffee. If it recommends no cafés, return an empty list.

<answer>
{answer}
</answer>"""


def extract_cafes(client, question: str, answer_text: str) -> tuple[list, dict]:
    """Returns ([{name, neighborhood}], usage)."""
    if not answer_text.strip():
        return [], {}
    r = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT.format(question=question, answer=answer_text)}],
    )
    usage = {"input_tokens": r.usage.input_tokens or 0, "output_tokens": r.usage.output_tokens or 0}
    if r.stop_reason in ("refusal", "max_tokens"):
        return [], usage
    text = next((b.text for b in r.content if b.type == "text"), "")
    cafes = json.loads(text).get("cafes", []) if text else []
    return [c for c in cafes if c.get("name", "").strip()], usage
