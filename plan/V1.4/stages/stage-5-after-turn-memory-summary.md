# V1.4 Stage 5: After-Turn MiMo Memory Summarization

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

After every completed text or voice conversation turn, enqueue a background
memory summarization job that can add, update, or delete validated lines in the
canonical notebook:

```text
backend/data/memory_cards/memory.md
```

The foreground response path must not wait for summarization. Text reply, audio
job enqueue, audio polling, and frontend action rendering stay on the existing
fast path.

## Scope

In scope:

- add a dedicated memory summarizer provider profile using only env-backed MiMo
  config;
- enqueue one after-turn summary job for completed text/voice turns;
- prioritize explicit memory triggers such as "记住";
- validate model-proposed add/update/delete operations before file writes;
- apply operations to canonical `memory.md` only;
- keep legacy explicit memory acknowledgment behavior;
- prove Fast Reply does not call the summarizer synchronously.

Out of scope:

- realtime speech-to-speech;
- using MiMo for fast reply, thinking reply, ASR, TTS, or tools;
- strict 10-line disk cap;
- changing nightly cleanup provider behavior beyond Stage 4 canonical target;
- frontend redesign.

## Provider Policy

Add a provider profile:

```yaml
memory_summarizer:
  name: mimo_memory_summarizer
  model_env: MIMO_MEMORY_MODEL
  default_model: mimo-v2.5
  base_url_env: MIMO_BASE_URL
  api_key_env: MIMO_API_KEY
```

The actual implementation should use the existing provider config loader shape
where practical. Secrets must remain in environment variables only.

If the memory summarizer provider is not configured, testing may use the mock
provider and production should fail the background job safely without affecting
the foreground response.

## Queue Policy

Use the existing in-memory background queue boundary where possible.

Jobs:

- `turn_summary` for every completed text/voice turn;
- legacy `judgment` jobs remain supported for compatibility tests.

Dedup:

- normalize `user_text`;
- include `pet_reply` in turn job dedup key so repeated "你好" with different
  outcomes is still allowed when useful;
- queue remains bounded.

Priority:

- explicit memory triggers append to the front of the queue;
- normal after-turn jobs append to the back;
- if the queue is full, explicit jobs may evict the oldest normal job, but must
  not block the current response.

## Summary Input

Include:

- latest user text;
- latest 豆豆 reply;
- route (`fast_reply` or `thinking`);
- selected memory hints from the turn context, bounded;
- bounded canonical `memory.md` content;
- trigger categories.

Do not include:

- current time;
- device state;
- tools;
- raw database dumps;
- API keys;
- raw provider errors.

## Summary Output

The model returns operations:

```json
{
  "add": [{"category": "preference", "content": "主人喜欢短回复。"}],
  "update": [
    {
      "old": "- [2026-05-29 10:00][project] 主人在调豆豆。",
      "new_category": "project",
      "new_content": "主人在调 PetAgent V1.4。"
    }
  ],
  "delete": [
    {
      "old": "- [2026-05-26 10:00][temporary] 主人今天有点忙。",
      "reason": "temporary expired"
    }
  ]
}
```

Backend validation:

- category whitelist;
- content length and sensitive-token filtering are enforced by
  `NotebookManager.apply_cleanup_operations()`;
- model content must not provide timestamps;
- all targets canonicalize to `memory.md`;
- malformed output is ignored safely.

## Acceptance Criteria

- every completed text/voice turn can enqueue a background summary job;
- Fast Reply returns before the summarizer provider is called;
- explicit memory triggers still return `memory_ack_hint`;
- explicit memory jobs are prioritized;
- memory summary operations write only to canonical `memory.md`;
- invalid output is ignored without crashing maintenance;
- MiMo summarizer config is isolated from chat/TTS/ASR providers;
- focused backend tests pass.
