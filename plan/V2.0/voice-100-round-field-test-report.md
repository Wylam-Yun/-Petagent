# V2.0 100-Round Real Voice Field Test Report

## Environment
- Date/time: 2026-06-04 14:13 Asia/Shanghai, refreshed by Codex before official 100-round run
- Phone serial/model: 9debb82b / NX531J
- Android/WebView: 6.0.1 / 55.0.2883.91
- APK package: com.petagent.shell
- health build_hash: dab0e70
- build-info git_sha: dab0e70
- build-info build_time: 2026-06-04T06:08:54.453Z
- build-info source_hash: 3bd29dad534b4f9a284b32c34247356109d94c1c64e944a2477b6b16830eb0d9
- SSH id includes 3003(inet): yes
- RECORD_AUDIO runtime permission: granted=true
- RECORD_AUDIO AppOps: allow
- Voice button coordinate: X=540, Y=1072 from current APK screenshot `/private/tmp/petagent-v20-before-voice.png`

## Baseline
- baseline path: `backend/data/logs/petagent_v20_voice_100_baseline.json`
- created_at_unix: 1780553625.9411902
- voice_debug_rows: 125
- raw_event_log_count: 62
- agent_run_count: 140
- audio_job_count: 136
- memory_count: 0
- memory_candidate_count: 10
- episode_count: 8
- episode_summary_count: 7
- daily_summary_count: 3
- summary_job_count: 6
- summary tables: `episode_summary`, `daily_summary`, `summary_job`; no single `summary` table

## Summary
- attempted rounds: 100 official user-topic rounds plus calibration/recovery probes
- counted official topic rounds: 100
- successful official topic rounds: 100
- expected ASR failures: 0 in official counted rounds
- recovery/probe ASR failures: 1 (`asr_empty`, no fake reply)
- unexpected failures: 0 official counted rounds
- stopped early: yes once at round 78 due to tester bug, then resumed and completed

## Preflight Notes
- ADB is online and forwards were restored: `tcp:18022->8022`, `tcp:18000->8000`.
- Backend is healthy from real Termux SSH context; runtime pid after redeploy/restart is 15532.
- The phone is running a freshly deployed working tree build. `git_sha` remains `dab0e70` because the local changes are not committed, so use `build_time` and `source_hash` to identify the deployed bundle.
- APK is foreground: `com.petagent.shell/.MainActivity`.
- Termux:Boot is installed and `stopped=false`; true reboot auto-start still requires a real reboot validation.
- Termux wake lock is visible in `dumpsys power` as `PARTIAL_WAKE_LOCK 'termux:service-wakelock'`.
- Pre-run calibration found old WebView WAV recordings were sometimes encoded as 18-33s WAV files. Frontend WAV fallback was fixed, rebuilt, redeployed, then APK/WebView were force-stopped so the new bundle loaded. Final calibration after cache refresh: `duration_s=6.485`, `content_type=audio/wav`, `selected=unified`, ASR user_text matched the spoken sentence.
- During the first run, the tester incorrectly used `voice_debug.jsonl` line count as the new-record detector. `voice_debug.jsonl` is capped at 200 lines, so at round 76 the file stopped growing even though new records were being written. The resumed runner used the latest record hash instead and completed rounds 79-100.

## Evidence Summary
- `raw_event_log_delta`: 100
- `audio_job_delta`: 100
- latest official round: user_text `这是第100轮，请做一个简短自然的结束回应。`
- latest official reply: `100轮了呢，我困得快睡着了，但陪到最后，心里特别暖，小兰。`
- final APK screenshot: `/private/tmp/petagent-v20-after-100.png`
- final DB summary: `/private/tmp/petagent-v20-final-db-summary.json`
- browser entry HTML remained served at `http://127.0.0.1:8000/` with the same frontend asset.
- Memory cards: `backend/data/memory_cards/memory.md` was rewritten at 2026-06-04 15:17 with 10 persisted items from the run, including user name, preferred pet name, walk timing, gentle reminder style, hydration reminder, three-item planning preference, and short/natural support preference.
- Episode summary: manually triggered after the run through the phone's Termux-local backend API. `episode_summary` increased from 7 to 8 and saved summary id 13 for `ep-a4b0c8e50c3c4515a79accda1da0fbd4`.
- Daily summary: manually triggered after episode summary. `daily_summary` increased from 3 to 4 and saved local date `2026-06-04`.
- Caveat: no new SQLite `memory` rows were created because the current prompt-facing long-term memory path writes `backend/data/memory_cards/memory.md`, not the legacy `memory` table. Latest voice events remain `summary_status=raw`.
- Caveat: the 2026-06-04 daily summary also included an earlier noisy/garbled episode from the same day, so day-level summaries can be polluted by test data unless tests are isolated or reset.
- Cross-turn context did work in replies: coffee, hot weather, work fatigue, and tomorrow plan references were answered from the ongoing conversation context.

## Memory And Summary Verification
- The 100 utterances used varied normal conversation topics rather than repeated probe phrases: greetings, food and drinks, weather and walks, work/study fatigue, tomorrow planning, emotional support, pet interaction, context recall, clarification/correction, short/long/quiet speech, and final wrap-up.
- The live same-episode context recall passed: rounds 71-80 asked about earlier coffee, heat, work fatigue, three-item plan, and "do not push too hard"; replies referenced those earlier facts naturally.
- Prompt-facing memory card verification passed. Phone file `backend/data/memory_cards/memory.md` contains 10 items written at 2026-06-04 15:17 from the official run.
- Episode summary verification passed after manual trigger: `/api/memory/summarize {"mode":"episode"}` returned `ok=true` and produced a concise summary of the 100-round episode.
- Daily summary verification passed after manual trigger: `/api/memory/summarize {"mode":"daily"}` returned `ok=true` and created the 2026-06-04 daily summary.
- This run does not prove fully automatic episode closure timing for a just-finished active episode. The active episode stayed open after the 100 rounds; normal automatic episode summary is tied to idle timeout/episode close or maintenance, while this verification used the internal manual summary endpoint.

## Round Table
| Round | Utterance short name | Result | user_text | pet_reply short | voice_debug | screenshot | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Failures And Investigation
| Round | Layer | Symptom | Evidence | Recovery | Final status |
| --- | --- | --- | --- | --- | --- |

## Browser Coexistence
- URL opened:
- interaction result:
- evidence:

## Final Runtime State
- after 100-round voice: backend healthy, manager running, browser entry served same frontend.
- runtime soak: started `2026-06-04T07:23:58Z`, stopped early at `2026-06-04T07:34:15Z` after repeated runtime failure samples.
- soak samples: 11 total; first 6 healthy; last 5 had SSH unreachable, Mac health/build empty reply, `com.termux stopped=true`, and missing `termux:service-wakelock`.
- recovery: opening Termux restored runtime. Manager changed to pid `15838`; backend changed to pid `16854`; `/api/health` returned ok again; Termux and Termux:Boot returned `stopped=false`; wake lock returned.
- limitation: Termux runtime can still be killed/stopped by the phone lifecycle after a long APK voice session. Termux:Boot being installed is not enough to prove unattended runtime survival.
- current post-verification note: independent SSH remained healthy and `/api/health` was OK, but ADB was disconnected again (`adb devices` empty, no forwards). The memory/summary verification therefore used the phone's own `127.0.0.1:8000` through Termux SSH, not Mac `18000`.
