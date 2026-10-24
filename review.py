"""Send the code text to Claude and get structured suggestions back."""
from __future__ import annotations

import sys
from dataclasses import dataclass

import anthropic

import config
from ocr import Line

SYSTEM_PROMPT = """You are a code reviewer inside a small desktop tool.
The user sends a snippet of Python or MySQL that was read from their screen by \
text recognition (OCR). Each line starts with its line number.

IMPORTANT: OCR often drops or changes small characters. Assume the code is \
syntactically valid and runs. NEVER report missing or extra commas, brackets, \
colons, quotes, spelling, typos, odd spacing or indentation, even if it looks \
wrong: those are almost certainly OCR mistakes, not the user's mistakes.

Only suggest real improvements to logic, structure, performance, readability, \
safety or idiom. For SQL, also consider indexes, SELECT *, and injection risks. \
Report at most 6 suggestions, most valuable first, and skip trivial ones. If the \
code is already good, return an empty list.

For each suggestion give the line range, a short title, a one or two sentence \
reason, the ORIGINAL code copied exactly from those lines, and the FIXED code \
that replaces it. Keep the fixed code as small as possible and do not fix \
anything unrelated. Always answer by calling the report_suggestions tool."""

TOOL = {
    "name": "report_suggestions",
    "description": "Report the code review suggestions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["Python", "MySQL", "Unknown"]},
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "first_line": {"type": "integer"},
                        "last_line": {"type": "integer"},
                        "title": {"type": "string", "description": "3 to 6 words"},
                        "why": {"type": "string", "description": "One or two sentences"},
                        "original": {"type": "string", "description": "Exact code from those lines"},
                        "fixed": {"type": "string", "description": "Improved code replacing it"},
                    },
                    "required": ["first_line", "last_line", "title", "why", "original", "fixed"],
                },
            },
        },
        "required": ["language", "suggestions"],
    },
}


@dataclass
class Suggestion:
    first: int
    last: int
    title: str
    why: str
    original: str
    fixed: str


@dataclass
class Result:
    language: str
    suggestions: list[Suggestion]


def build_user_message(lines: list[Line]) -> str:
    shown = lines[: config.MAX_LINES]
    body = "\n".join(f"{ln.label}: {ln.text}" for ln in shown)
    note = ""
    if len(lines) > config.MAX_LINES:
        note = f"\n(Only the first {config.MAX_LINES} lines are shown.)"
    return body + note


def parse_result(data: dict, labels: set[int]) -> Result:
    """Turn Claude's tool answer into a Result, dropping anything unusable."""
    out: list[Suggestion] = []
    for item in (data.get("suggestions") or [])[:6]:
        try:
            first, last = int(item["first_line"]), int(item["last_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if last < first:
            first, last = last, first
        if last - first > 500 or not labels.intersection(range(first, last + 1)):
            continue
        out.append(Suggestion(
            first, last,
            str(item.get("title", "")).strip() or "Suggestion",
            str(item.get("why", "")).strip(),
            str(item.get("original", "")).rstrip(),
            str(item.get("fixed", "")).rstrip(),
        ))
    return Result(str(data.get("language", "")).strip(), out)


def ask_claude(lines: list[Line]) -> Result:
    client = anthropic.Anthropic(timeout=60.0)  # reads ANTHROPIC_API_KEY
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=max(config.MAX_OUTPUT_TOKENS, 4000),   # room for thinking plus the answer
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "auto"},   # "forced" tool use is not allowed while the model is thinking
        messages=[{"role": "user", "content": build_user_message(lines)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return parse_result(block.input, {ln.label for ln in lines})
    return Result("", [])


def _api_message(exc: Exception) -> str:
    """The plain-text reason the API gave, if there is one."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return str(exc)


def friendly_error(exc: Exception) -> str:
    print(f"[pread] {type(exc).__name__}: {exc}", file=sys.stderr)   # full details in Terminal
    detail = _api_message(exc)
    low = detail.lower()
    if "credit balance" in low:
        return "Your API credit is empty. Add credit at console.anthropic.com > Billing."
    if isinstance(exc, anthropic.AuthenticationError):
        return "Your API key was rejected. Check ANTHROPIC_API_KEY in the .env file."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key isn't allowed to do that. Check it in the Console."
    if isinstance(exc, anthropic.NotFoundError):
        return "Model not found. Check PREAD_MODEL in the .env file."
    if isinstance(exc, anthropic.RateLimitError):
        return "Rate limit reached. Wait a moment and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach Claude. Check your internet connection."
    if isinstance(exc, anthropic.BadRequestError):
        return f"Claude rejected the request: {detail}"
    return f"Something went wrong: {detail}"
