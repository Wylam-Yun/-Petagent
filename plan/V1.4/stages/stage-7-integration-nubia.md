# V1.4 Stage 7: Integration, Nubia Deployment, And Live API Verification

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Prove V1.4 is complete against the real target device. Local tests are not
enough; the connected Nubia phone must run the deployed code and pass live API
checks.

## Scope

In scope:

- run targeted frontend and backend regression tests;
- build frontend production bundle;
- deploy current runtime/frontend/config to Nubia;
- restart Termux runtime cleanly;
- verify `/api/health` build hash;
- run manual Fast Reply and memory-trigger API checks;
- poll audio job readiness;
- run `backend/tests/test_live_nubia.py`;
- inspect real Nubia notebook files after migration;
- record results in completion docs;
- commit and push final docs.

Out of scope:

- frontend redesign;
- production use of generated action art;
- adding realtime speech-to-speech;
- reintroducing tools/weather/retrieval.

## Verification Commands

Local:

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
pytest backend/tests/test_fast_reply_contract.py \
  backend/tests/test_text_chat.py \
  backend/tests/test_voice_pipeline.py \
  backend/tests/test_notebook.py \
  backend/tests/test_nightly_cleanup.py \
  backend/tests/test_stage5_behavior.py \
  backend/tests/test_memory_judgment.py \
  backend/tests/test_config_loader.py \
  backend/tests/test_memory_cards.py -q
```

Nubia:

```bash
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
adb forward tcp:18000 tcp:8000
curl http://127.0.0.1:18000/api/health
curl http://127.0.0.1:18000/api/health/watchdog
pytest backend/tests/test_live_nubia.py -q --tb=short
```

Manual live API probes:

- text Fast Reply with audio job polling;
- explicit memory trigger with `memory_ack_hint`;
- notebook file inspection through `adb shell run-as com.termux`.

## Acceptance Criteria

- local frontend tests pass;
- local frontend build passes;
- targeted backend regression passes;
- Nubia `/api/health` reports the deployed runtime commit;
- Nubia watchdog is healthy and not stuck;
- Fast Reply returns route/action without leaked reasoning;
- audio job reaches `ready` or another safe terminal state;
- explicit memory trigger returns `memory_ack_hint`;
- canonical Nubia notebook is `backend/data/memory_cards/memory.md`;
- live test suite passes;
- completion document records results and residual risks.
