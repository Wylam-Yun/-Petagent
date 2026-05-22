# Phase 4 Live Follow-up: Watchdog Idle False Positive

**Date:** 2026-05-22
**Mode:** strict follow-up after Nubia live validation
**Base commit reviewed:** `b091f18`

## Scope

This follow-up is limited to the live issue found after Phase 4 deployment:
`/api/health/watchdog` reports `stuck=true` after normal idle time because
`event_loop_tick_age_s` is currently the age of the last pet event, not an
event-loop heartbeat.

Covered requirement: STAB-033/STAB-036 watchdog correctness for long-running
Android 6 deployment.

## Finding

On Nubia after updating to `b091f18`, health and live API passed, but an idle
runtime produced:

```json
{"event_loop_tick_age_s":279.3,"stuck":true}
```

Manager then logged:

```text
PetAgent watchdog reports stuck (1/3)
Frontend heartbeat stale (...); relaunching browser
```

This is a false positive. A quiet Momo with no recent user/pet event must not be
restarted by the manager.

## Implementation Plan

1. Run read-only plan review against this follow-up, the master plan, Phase 1
   watchdog plan, current code, and Nubia observation.
2. Add a lightweight async heartbeat task in `backend/app/main.py` lifespan:
   - Update `dispatcher.event_loop_tick` every second while the app is running.
   - Keep the existing `handle_event()` tick update.
   - Cancel and await the heartbeat task on shutdown.
   - Do not touch provider gates, health endpoint shape, manager script, or pet
     response behavior.
3. Add regression coverage in `backend/tests/test_phase1_watchdog.py`:
   - Without lifespan, a manually stale tick still reports `stuck=true` for the
     existing synthetic stuck test.
   - With lifespan active, an artificially stale tick is refreshed by the
     heartbeat and watchdog returns `stuck=false`.
4. Run verification:
   - `cd backend && ../.venv/bin/python -m pytest tests/test_phase1_watchdog.py tests/test_phase1_startup.py -q`
   - `cd backend && ../.venv/bin/python -m pytest -q`
5. Run completion review with a read-only subagent.
6. Fix review findings if needed and rerun relevant tests.
7. Write compact handoff summary here.
8. Commit and push this follow-up.
9. Deploy latest to Nubia and rerun:
   - health/watchdog after >120s idle, expecting `stuck=false`
   - `tests/test_live_nubia.py`

## Rollback Notes

If the async heartbeat causes shutdown noise, keep the heartbeat update but
shorten cancellation handling. If the heartbeat causes unexpected CPU overhead,
raise its interval from 1s to 5s. Do not return to treating normal idle time as
watchdog-stuck.

## Plan Review

Read-only subagent plan review returned `PASS`:

```json
{"verdict":"PASS","findings":[],"notes":["Plan is narrowly scoped to STAB-033/STAB-036 watchdog correctness.","Async lifespan heartbeat is appropriate: normal idle no longer looks stuck, while true event-loop stalls still age out because the heartbeat task stops running."]}
```

## Completion Review

Read-only subagent completion review returned `PASS`:

```json
{"verdict":"PASS","findings":[],"checks":{"normal_idle_not_stuck":"PASS","true_event_loop_stall_detectable":"PASS","api_shape_changes":"PASS","manager_changes":"PASS","pet_behavior_changes":"PASS","android6_overhead":"PASS"}}
```

Verification:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_phase1_watchdog.py tests/test_phase1_startup.py -q
# 12 passed in 1.57s

cd backend && ../.venv/bin/python -m pytest -q
# 541 passed, 24 skipped in 20.32s
```

## Compact Handoff

Follow-up changed:

- `backend/app/main.py` starts a low-cost async lifespan heartbeat that updates
  `dispatcher.event_loop_tick` once per second and cancels it on shutdown.
- Existing watchdog response shape is unchanged.
- Synthetic stale tick tests still prove `stuck=true` outside lifespan.
- New lifespan regression proves a live, idle runtime refreshes the heartbeat
  and returns `stuck=false`.

Nubia:

- Deploy latest commit after push.
- Rebuild/sync frontend dist only if the commit changes frontend sources; this
  follow-up is backend-only.
- Restart manager/runtime.
- Verify `/api/health/watchdog` after >120s idle stays `stuck=false`.
- Rerun `backend/tests/test_live_nubia.py` on-device.
