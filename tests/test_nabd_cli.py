# -*- coding: utf-8 -*-
"""The command a juror types first, and what happens when the room is not ours.

`python -m nabd.scene` is the README's first line. It has to work on bare
Python, print something a person can read, leave the evidence exactly as it
was committed, and fail in sentences rather than tracebacks when a transcript
is missing or a language model is misconfigured.

Plain functions, no fixtures: `python -m tests.run` calls each with no
arguments, and so does the public export's self-check.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nabd import llm, scene  # noqa: E402
from nabd.gateway import EVIDENCE_DIR  # noqa: E402


@contextlib.contextmanager
def env(**values):
    """Set environment variables for the block; None removes one. Restored after."""
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scene.main(argv)
    return code, out.getvalue(), err.getvalue()


def test_the_first_command_runs_and_leaves_the_evidence_byte_identical():
    path = EVIDENCE_DIR / "nabd-scene-noise.jsonl"
    before = path.read_bytes()
    code, out, _ = run_main(["--scene", "noise", "--runner", "loop"])
    assert code == 0
    assert "ABSTAIN" in out
    assert "evidence      nabd-scene-noise.jsonl" in out
    assert "abstentions   3" in out
    assert path.read_bytes() == before, "running the demo must not move the evidence it was made from"


def test_verbose_prints_the_signals_and_the_camara_tally():
    code, out, _ = run_main(["--scene", "quake", "--runner", "loop", "-v"])
    assert code == 0
    assert "├─" in out and "CAMARA:" in out
    assert "privacy gate" in out


def test_auto_runner_falls_back_to_the_loop_without_langgraph():
    import nabd.graph as graph

    had = graph.LANGGRAPH_AVAILABLE
    graph.LANGGRAPH_AVAILABLE = False
    try:
        code, out, err = run_main(["--scene", "quiet"])
    finally:
        graph.LANGGRAPH_AVAILABLE = had
    assert code == 0
    assert "runner: loop" in out
    assert "langgraph is not installed" in err


def test_auto_runner_uses_the_graph_when_it_is_there():
    import nabd.graph as graph

    if not graph.LANGGRAPH_AVAILABLE:
        return  # nothing to check on a bare interpreter
    code, out, _ = run_main(["--scene", "quiet"])
    assert code == 0
    assert "runner: graph" in out


def test_a_missing_transcript_is_a_sentence_not_a_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            scene.run_replay(transcript=Path(tmp) / "never-recorded.jsonl", out=io.StringIO())
        except SystemExit as stop:
            assert "does not exist" in str(stop)
            assert "--backend live" in str(stop)
        else:
            raise AssertionError("a missing transcript must stop the run with a message")


def test_a_misconfigured_model_is_reported_and_the_template_is_used():
    with env(NABD_LLM="groq", GROQ_API_KEY=None):
        report = io.StringIO()
        assert llm.from_env(report=report) is None
        assert "GROQ_API_KEY is not set" in report.getvalue()
        assert "template used" in report.getvalue()
    with env(NABD_LLM="bogus"):
        report = io.StringIO()
        assert llm.from_env(report=report) is None
        assert "unknown provider" in report.getvalue()
    with env(NABD_LLM=""):
        assert llm.from_env(report=io.StringIO()) is None


def test_msisdns_parses_a_comma_list_with_spaces():
    from nac import client

    with env(NAC_MSISDNS=" +3670001, +3670002 ,, +3670003 "):
        assert client.msisdns() == ["+3670001", "+3670002", "+3670003"]
    with env(NAC_MSISDNS=""):
        assert client.msisdns() == []


def test_the_shell_wins_over_the_env_file():
    """The real environment beats nac/.env, which may hold someone else's key."""
    from nac import client

    with env(NAC_API_KEY="from-the-shell"):
        assert client.api_key() == "from-the-shell"


def test_the_live_client_has_a_short_timeout():
    """Sixty seconds a call, two hundred calls a pass: a hung platform must not
    stall the agent for hours. Ten seconds by default, settable, never zero."""
    from nac import client

    with env(NAC_TIMEOUT_S=None):
        assert client.timeout_s() == 10.0
    with env(NAC_TIMEOUT_S="2.5"):
        assert client.timeout_s() == 2.5
    for bad in ("0", "-3", "soon"):
        with env(NAC_TIMEOUT_S=bad):
            try:
                client.timeout_s()
            except ValueError:
                pass
            else:
                raise AssertionError(f"{bad!r} must be refused")
    with env(NAC_TIMEOUT_S="4", NAC_API_KEY="not-a-real-key"):
        try:
            api = client.build()
        except ImportError:
            return  # the SDK is not installed here; nothing to wire
        assert api._client_wrapper.get_timeout() == 4.0
