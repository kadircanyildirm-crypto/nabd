"""Every suite, one command: `python -m tests.run`.

No test runner is required and none is imported. That is a deliberate
constraint rather than a preference: the one thing that must not happen in the
week before a demonstration is discovering that the suite needs a wheel the
machine in the room cannot install. Each suite is also runnable on its own —
`python -m tests.test_nabd_detector` — so a failing invariant can be isolated.

    test_nabd_detector     the core: correlate → exclude → declare, plus two fuzzed invariants
    test_nabd_scenes       the five scenes end to end, and the two runners diffed byte for byte
    test_nabd_parity       one agent, every backend, proven by replay
    test_nabd_real         the agent against two earthquakes that happened, the second untouched
    test_nabd_live_wiring  the live path resolved against the installed Nokia SDK, no calls spent
    test_nabd_llm          the language model's guard: phrase the facts, never invent a number
    test_nabd_false_alarm  the false-alarm rate as a number, under random sentinel dropout
    test_nabd_provenance   every number the film says, traced to its source
    test_nabd_blind        the platform's silence is not the network's: blind passes abstain, clear nothing
    test_nabd_cli          the first command a juror types: deterministic evidence, failures as sentences
"""

from __future__ import annotations

import importlib
import sys

SUITES = (
    "tests.test_nabd_detector",
    "tests.test_nabd_scenes",
    "tests.test_nabd_parity",
    "tests.test_nabd_real",
    "tests.test_nabd_live_wiring",
    "tests.test_nabd_llm",
    "tests.test_nabd_false_alarm",
    "tests.test_nabd_provenance",
    "tests.test_nabd_blind",
    "tests.test_nabd_cli",
)


def main(suites: list[str] | None = None) -> int:
    suites = list(suites) if suites else list(SUITES)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    failures = 0
    total = 0
    for name in suites:
        module = importlib.import_module(name)
        tests = [v for k, v in sorted(vars(module).items()) if k.startswith("test_") and callable(v)]
        print(f"\n  {name.split('.')[-1]}  ({len(tests)} tests)")
        print("  " + "─" * 62)
        for test in tests:
            total += 1
            try:
                test()
                print(f"  ok    {test.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {test.__name__}\n          {exc}")
            except Exception as exc:  # a suite that errors is a failure, not a crash
                failures += 1
                print(f"  ERROR {test.__name__}\n          {type(exc).__name__}: {exc}")

    print("\n" + "═" * 66)
    print(f"  {total - failures}/{total} passed across {len(suites)} suites")
    print("═" * 66)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or None))
