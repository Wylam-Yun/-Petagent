# V1.4 Stage 7 Completion: Integration, Nubia Deployment, And Live API

**Date:** 2026-05-29
**Deployed commit:** `274abfa`

## Result

Stage 7 is complete. V1.4 was deployed to the connected Nubia device, the
runtime started cleanly, live API tests passed, and the real notebook files on
the phone were verified after migration.

Two final migration fixes were added during integration:

- `591a52f Finalize V1.4 notebook migration`
  - resolves notebook card paths against `project_root`;
  - finalizes header-only or partially migrated old card files into V1.4
    `memory.md`;
  - keeps `user.md` as a stub.
- `274abfa Import legacy misresolved notebooks`
  - imports valid entries from the old wrong path
    `backend/backend/data/memory_cards`;
  - marks that wrong path as imported so it is no longer read.

## Local Verification

Frontend:

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Result:

```text
17 files, 136 tests passed
frontend build passed
```

Backend targeted V1.4 regression:

```bash
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

Result:

```text
140 passed
```

Additional focused migration checks:

```bash
pytest backend/tests/test_notebook.py backend/tests/test_memory_cards.py -q
```

Result:

```text
59 passed
```

## Nubia Deployment

Deploy command:

```bash
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
```

Runtime restart:

```bash
adb shell 'run-as com.termux sh -c "cd files/home/Petagent && ... ./scripts/stop.sh; ... ./scripts/start.sh"'
```

Health:

```text
/api/health ok=true
name=豆豆
build_hash=274abfa
/api/health/watchdog ok=true stuck=false audio_queue_depth=0
```

## Live API Checks

Manual Fast Reply text check:

```text
text: 早上好豆豆，今天轻声一点陪我聊。
latency_ms: 2644
route: fast_reply
action: lazy_idle
reply: 早呀～今天要轻声说话哦，豆豆还在偷懒打盹呢。
audio_job: ready
tts_ms: 1811
```

Manual memory trigger check:

```text
text: 记住我现在希望快速模式也要记得十条重要小本本。
latency_ms: 2516
route: fast_reply
action: remember
memory_ack_hint: 我先记到小本本
```

Automated live suite:

```bash
PETAGENT_TEST_URL=http://127.0.0.1:18000 \
PETAGENT_INTERNAL_TOKEN_FILE=/tmp/petagent-token... \
pytest backend/tests/test_live_nubia.py -q --tb=short
```

Result:

```text
21 passed in 19.86s
```

## Notebook Verification On Nubia

Canonical notebook:

```text
backend/data/memory_cards/memory.md
<!-- v1.4_single_notebook -->
```

Verified contents include:

- imported legacy relationship memory from real old `user.md`;
- imported entries from the old wrong `backend/backend/data/memory_cards` path;
- fast-mode preference: `用户希望快速模式也要记得十条重要小本本。`

Compatibility stub:

```text
backend/data/memory_cards/user.md
<!-- v1.4_single_notebook_stub: canonical memory is memory.md -->
```

Old wrong path after import:

```text
backend/backend/data/memory_cards/memory.md
<!-- v1.4_misresolved_notebook_imported: canonical memory is memory.md -->
```

## Completion Review

No blocker remains.

The original live symptom of missing reply/audio was not reproduced after the
network came back and V1.4 was deployed. On the final device build, text chat
returned in about 2.5-2.6 seconds and audio job generation reached `ready`.

The final integration issue was data migration, not model latency: old preserved
Nubia files plus a previous relative-path bug left memory in two locations. The
startup migration now resolves notebook paths from project root and imports the
old wrong-path entries once.

## Residual Risks

- After-turn memory summary is still asynchronous and in-memory; pending summary
  jobs can be lost on process restart.
- Summarizer quality depends on MiMo output, but unsafe or malformed operations
  are rejected before writing `memory.md`.
- Live voice recording from the physical UI was not manually exercised in this
  final pass; the live suite and manual text/audio polling covered backend
  routing and TTS job readiness.

## Acceptance Criteria Audit

- Full targeted local tests passed: yes.
- Nubia deployed commit matches current code: yes, `274abfa`.
- `/api/health` and `/api/health/watchdog` pass: yes.
- Live Fast Reply check passes: yes.
- Live memory trigger check passes: yes.
- Audio job reaches terminal safe state: yes, `ready`.
- Response route/action fields present: yes.
- No leaked reasoning observed in manual live replies: yes.
- Notebook is canonical V1.4 `memory.md` on the phone: yes.
- Live API suite passes on Nubia: yes, `21 passed`.
