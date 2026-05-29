# V1.4 Stage 3: Autonomous Idle Life

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Make 豆豆 feel alive when the user has not interacted for a while. Idle time
should show small life activities such as lounging, napping, secretly eating,
watching TV, grooming, or wandering, without interrupting active listening,
speaking, audio waiting, errors, or text/voice work.

## Scope

In scope:

- frontend-local volatile idle activity state;
- short idle activities after a modest delay;
- stronger idle activities after a longer delay;
- record `last_idle_activity` for return reactions;
- user return/tap can produce a small reaction based on the interrupted idle
  activity;
- deterministic test hooks through injected random/time arguments already used
  by `BehaviorDirector`.

Out of scope:

- writing idle state to backend memory;
- LLM-generated idle behavior;
- changing backend proactive scheduler;
- final new sprite art.

## Timing

Keep Nubia modest:

- existing 5s ambient tick remains;
- no idle activity during the first 60s after user input;
- short idle activities may occur after 60s;
- long idle activities may occur after 5 minutes;
- after one idle activity, schedule the next one 20-45s later.

For tests, `onAmbientTick(now, ...)` already receives explicit time, and
activity selection can be made deterministic by overriding `Math.random`.

## Activity Set

Short idle:

```text
lazy_idle, self_groom, wander
```

Long idle:

```text
nap, sneak_eat, watch_tv
```

The selected activity is stored as volatile runtime state:

```text
last_idle_activity
last_idle_activity_at
```

This is not long-term memory.

## Interruption / Return Rules

When the user taps 豆豆 after an idle activity:

- `nap` -> `confused`, sleepy bubble;
- `sneak_eat` -> `tease`, guilty/denial bubble;
- `watch_tv` -> `pretend_busy`, interrupted bubble;
- `wander` -> `greet`, happy return bubble;
- `lazy_idle` -> `lazy_idle`, lazy excuse bubble;
- `self_groom` -> `happy`, calm bubble.

If the UI is in a protected phase, protected-phase behavior still wins.

## Acceptance Criteria

- No autonomous activity during listening, waiting voice, speaking, errors, or
  busy state.
- No autonomous activity before the 60s idle threshold.
- Short idle activities happen after the short threshold.
- Long idle activities are eligible after 5 minutes.
- Return/tap reaction reflects the last idle activity.
- Idle state is cleared after the return reaction.
- Frontend tests pass.
