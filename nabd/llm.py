"""The language model, bound to the one node that may use it — and watched.

`nabd/brief.py` computes the facts of a pass and hands them to a composer,
which turns them into the sentence a duty officer reads. Offline that composer
is a template. With a key in the environment it is a model, and this module is
where the model is reached and where it is kept honest.

Providers
---------
The hackathon's Resource & Tooling Guide lists the free routes to a model, and
all four of them speak the same OpenAI-style chat endpoint, so one small
client covers them without a wheel to install:

    NABD_LLM=groq        GROQ_API_KEY         llama-3.3-70b-versatile
    NABD_LLM=gemini      GEMINI_API_KEY       gemini-2.0-flash
    NABD_LLM=openrouter  OPENROUTER_API_KEY   meta-llama/llama-3.3-70b-instruct:free
    NABD_LLM=ollama      (none, local)        llama3.2

`NABD_LLM_MODEL` overrides the model. Nothing else in the package reads any of
these: the detector, the triage and the gateway never see a model.

The guard
---------
The composer's contract is "phrase the facts, never invent them", and a
contract nobody checks is a hope. `guarded()` wraps a model composer and reads
the sentence back: every number in it — a cell count, an area, a confidence, a
person's id, a distance — has to be a number that was in the facts. If the
model adds one, its sentence is thrown away and the template speaks instead,
and the record says so. Being wrong here costs a sentence, not a decision,
which is exactly why this is the one place a model belongs; the guard is what
keeps it costing only a sentence.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

from nabd.brief import Composer, template

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "gemini-2.0-flash"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free"),
    "ollama": ("http://localhost:11434/v1/chat/completions", None, "llama3.2"),
}

SYSTEM = (
    "You write one short brief for the duty officer of a disaster command centre. "
    "You are given the facts of one pass as JSON. Phrase them in at most three plain sentences, "
    "most urgent first. Use only the numbers, cell ids, person ids and words that appear in the facts; "
    "never add, round, estimate or infer a number. If the facts say nothing happened, say so in one sentence."
)

# A number, a decimal, or an id built on one: 21, 4.0, E5, F10, R-031. A trailing
# unit or compass letter ("37.5858N", "4.0km") ends a number rather than breaking
# it, so the template's own phrasing passes its own guard.
NUMBER = re.compile(r"(?<![A-Za-z0-9])[A-Z]-?\d{1,3}(?!\d)|(?<![\w.])\d+(?:[.,]\d+)?(?!\d|[.,]\d)")


def numbers_in(text: str) -> set[str]:
    """Every number-like token in a sentence: 21, 4.0, R-031, E6-style cell ids."""
    out: set[str] = set()
    for m in NUMBER.finditer(text):
        tok = m.group(0).replace(",", ".")
        out.add(tok)
    return out


def numbers_of(facts: dict[str, Any]) -> set[str]:
    """The numbers a faithful sentence may use, harvested from the facts."""
    out: set[str] = set()

    def walk(v: Any) -> None:
        nonlocal out
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            out.add(str(v))
            if isinstance(v, float) and v == int(v):
                out.add(str(int(v)))
            if isinstance(v, int):
                out.add(f"{v}.0")
        elif isinstance(v, str):
            out |= numbers_in(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(facts)
    # Derived figures the template itself is allowed to say.
    if "cells" in facts:
        out.add(str(len(facts["cells"])))
    if facts.get("registry"):
        out.add(str(len(facts["registry"].get("first", []))))
    return out


def faithful(text: str, facts: dict[str, Any]) -> tuple[bool, set[str]]:
    """Did the sentence stay inside the facts? Returns (ok, the numbers it invented)."""
    allowed = numbers_of(facts)
    invented = {n for n in numbers_in(text) if n not in allowed and n.rstrip("0").rstrip(".") not in allowed}
    return (not invented), invented


def guarded(model: Composer, *, name: str = "model", report=None) -> Composer:
    """Wrap a model composer so it can phrase the facts but never invent them."""

    def compose(facts: dict[str, Any]) -> str:
        try:
            text = (model(facts) or "").strip()
        except Exception as exc:  # the network is not the agent's problem
            _say(report, f"[{name}] unavailable ({exc.__class__.__name__}); template used")
            return template(facts)
        ok, invented = faithful(text, facts)
        if not text or not ok:
            why = f"invented {sorted(invented)}" if invented else "empty"
            _say(report, f"[{name}] rejected ({why}); template used")
            return template(facts)
        return text

    return compose


def _say(report, line: str) -> None:
    if report is not None:
        print(line, file=report)


def chat(provider: str, model: str | None = None, timeout: float = 20.0) -> Composer:
    """An OpenAI-style chat call against one of the approved providers."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; one of {', '.join(PROVIDERS)}")
    url, key_var, default_model = PROVIDERS[provider]
    key = os.environ.get(key_var) if key_var else None
    if key_var and not key:
        raise RuntimeError(f"{key_var} is not set")
    model = model or os.environ.get("NABD_LLM_MODEL") or default_model

    def call(facts: dict[str, Any]) -> str:
        body = json.dumps({
            "model": model,
            "temperature": 0.2,
            "max_tokens": 180,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
            ],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    call.__name__ = f"{provider}/{model}"
    return call


def from_env(report=sys.stderr) -> Composer | None:
    """The composer the environment asks for, guarded — or None for the template."""
    provider = os.environ.get("NABD_LLM", "").strip().lower()
    if not provider:
        return None
    try:
        raw = chat(provider)
    except (ValueError, RuntimeError) as exc:
        # An unknown provider or a missing key must not stop the demo: the
        # template writes the brief, and the reason is said once.
        _say(report, f"[{provider}] not used ({exc}); template used")
        return None
    return guarded(raw, name=raw.__name__, report=report)
