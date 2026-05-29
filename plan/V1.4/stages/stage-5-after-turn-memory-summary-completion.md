# V1.4 Stage 5 Completion: After-Turn Memory Summarization

**Date:** 2026-05-29
**Commit:** `0bf8688`

## Result

Stage 5 adds after-turn background memory summarization. Every completed
text/voice conversation turn now enqueues a bounded background summary job. The
foreground response path only enqueues data; it does not call the summarizer
provider before returning the reply or enqueueing audio.

The summarizer proposes add/update/delete operations. The backend validates and
applies those operations to canonical `memory.md` only.

## Changed Files

- `config/models.yaml`
  - adds dedicated `memory_summarizer` provider profile;
  - uses `MIMO_BASE_URL`, `MIMO_API_KEY`, and `MIMO_MEMORY_MODEL` env-backed
    config.
- `backend/app/config.py`
  - loads optional `memory_summarizer`;
  - supports `model_env` with `default_model`.
- `backend/app/main.py`
  - selects a dedicated memory summarizer provider;
  - wires notebook manager into the background queue;
  - exposes notebook/queue on `app.state` for tests and diagnostics.
- `backend/app/pet/prompt_builder.py`
  - adds after-turn memory summary prompt and operation schema.
- `backend/app/runtime/memory_judgment.py`
  - extends the old judgment queue into a mixed background queue;
  - supports `turn_summary` jobs;
  - prioritizes explicit memory-trigger jobs;
  - validates model operations before maintenance applies them.
- `backend/app/runtime/dispatcher.py`
  - enqueues after-turn summary jobs after commit, outside the event lock;
  - preserves explicit memory acknowledgment UX.
- `backend/app/runtime/maintenance.py`
  - processes memory summary jobs before nightly cleanup;
  - applies validated operations through `NotebookManager`.
- `backend/app/runtime/notebook.py`
  - rejects model-provided timestamps in cleanup add/update content;
  - deduplicates add operations;
  - supports update/delete by content when the model gives a line content match.
- Backend tests updated for provider isolation, queue priority, foreground
  non-blocking behavior, and notebook writes.

## Verification

Compile check:

```bash
python -m py_compile \
  backend/app/config.py \
  backend/app/main.py \
  backend/app/pet/prompt_builder.py \
  backend/app/runtime/memory_judgment.py \
  backend/app/runtime/dispatcher.py \
  backend/app/runtime/maintenance.py \
  backend/app/runtime/notebook.py
```

Focused backend tests:

```bash
pytest \
  backend/tests/test_config_loader.py \
  backend/tests/test_memory_judgment.py \
  backend/tests/test_fast_reply_contract.py \
  backend/tests/test_notebook.py \
  backend/tests/test_nightly_cleanup.py \
  backend/tests/test_stage5_behavior.py
```

Result:

```text
87 passed
```

## Completion Review

No blocker found.

The critical latency requirement is covered: `test_fast_reply_enqueues_memory_summary_without_calling_provider`
proves Fast Reply returns with a queued summary job while the summarizer provider
call count remains zero.

The cleanup/write path remains canonical-only: all operations are converted to
`memory.md`, then filtered by existing notebook validation.

Explicit "记住" still gets a user-visible acknowledgment, but actual write work
is now background work.

## Risks Carried Forward

- The queue is in-memory and can lose pending summaries on process restart. This
  matches the existing maintenance pattern and avoids foreground latency.
- The first live Nubia check still needs to validate real MiMo env config and
  provider behavior.
- Summarizer quality depends on MiMo output; the backend rejects malformed or
  unsafe output but cannot guarantee every useful memory is captured.

## Acceptance Criteria Audit

- Every completed text/voice turn can enqueue a background summary job: yes.
- Fast Reply returns before summarizer provider call: yes.
- Explicit memory triggers still return `memory_ack_hint`: yes.
- Explicit jobs are prioritized and can evict normal jobs when full: yes.
- Summary operations write only to canonical `memory.md`: yes.
- Invalid output is ignored safely: yes.
- Model timestamps, duplicates, sensitive/overlong content are rejected: yes.
- MiMo summarizer config is isolated from chat/TTS/ASR: yes.
- Focused backend tests pass: yes.
