# Stage 5 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-5-after-turn-memory-summary.md`
- `backend/app/runtime/dispatcher.py`
- `backend/app/runtime/memory_judgment.py`
- `backend/app/runtime/maintenance.py`
- `backend/app/runtime/notebook.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/main.py`
- `config/models.yaml`
- related tests.

## Findings

No blocker found.

The existing `MemoryJudgmentQueue` already gives us the right background
boundary: bounded in-memory queue, provider gate, and maintenance-worker
processing. Reusing and extending it is safer than introducing a second
background scheduler.

The main compatibility concern is existing explicit-trigger behavior. The
dispatcher currently enqueues only user text and returns `memory_ack_hint` for
"记住" messages. Stage 5 can preserve that UX by enqueuing a richer after-turn
job while keeping the same acknowledgment string.

The second concern is foreground latency. The implementation must enqueue only
plain data after commit. No summarizer provider call may happen inside
`RuntimeDispatcher._handle_event_split()`. Tests should assert that the provider
is not called until maintenance processes the queue.

The third concern is provider isolation. `memory_summarizer` should be loaded as
a separate provider config. It may point at MiMo env vars, but changing it must
not alter fast reply, thinking reply, ASR, or TTS providers.

## Decision

Proceed with Stage 5 implementation locally. Claude is not used for planning or
review.
