# nac/

The Nokia Network-as-Code client Nabd calls, and the real responses it recorded.

Nothing here is the product. This is the instrument, and the source of the API
responses under `evidence/`.

| File | What it is |
|---|---|
| `client.py` | builds the SDK client from `nac/.env` — key, base URL, RapidAPI host, a per-call timeout — and resolves endpoint names that have moved between SDK releases |
| `.env.example` | the variables the live backend needs; copy to `.env`, which is git-ignored |
| `requirements.txt` | the SDK, pinned, and `python-dotenv` |
| `evidence/nabd-live-contract.jsonl` | the contract run of 10 September 2026 against the platform's simulator devices — 18 calls, request and response, verbatim |
| `evidence/nabd-live-log.jsonl` | the agent's verdicts on that run |
| `evidence/nabd-scene-*.jsonl` | the six scenes' evidence, one record per pass, written by `nabd/log.py` |

```bash
python -m nabd.scene --backend replay   # re-run the agent over the recorded live responses: no key, no network
python -m nabd.parity                   # the live transcript through the live parsers, evidence identical
python -m tests.test_nabd_live_wiring   # every endpoint resolved against the installed SDK, no call spent
cp nac/.env.example nac/.env            # then fill NAC_API_KEY and NAC_MSISDNS for a live run
python -m nabd.scene --backend live
```
