# V2.0 100-Round Real Voice Field Test Plan

> **For agentic workers:** REQUIRED FLOW: execute this plan task-by-task in a read-only testing loop. Do not modify app code. You may create/update test notes under `plan/V2.0/` only, and you may store screenshots under `/tmp` or `/private/tmp`.

**Goal:** Run 100 consecutive real Nubia voice turns through the installed PetAgent APK and verify whether the long voice conversation path stays correct.

**Architecture:** PetAgent runs on a Nubia Android phone in Termux. The backend is FastAPI on the phone at `http://127.0.0.1:8000`; the React/Vite frontend is served from that same backend. The Android APK is only a WebView shell (`com.petagent.shell`) that checks phone-local health, loads `http://127.0.0.1:8000/`, requests microphone permission, and sends voice through the existing frontend path to `/api/voice/chat`.

**Test Method:** Use ADB from the Mac to tap the Nubia UI. Use the Mac `say` command as the user's voice source, played near the Nubia microphone while the APK is recording. This is a real device microphone test, not a direct `curl` upload.

---

## Hard Rules

- Do not edit code, frontend assets, backend code, Android code, build files, or runtime scripts.
- Do not rebuild, reinstall, or redeploy unless the owner explicitly asks.
- Do not add a new voice endpoint. Voice must continue through existing `/api/voice/chat`.
- Do not use browser logs or old voice records as proof for these 100 rounds.
- Do not use direct `curl /api/voice/chat` upload as the main test.
- Do not use ADB/root/su as runtime support for the backend.
- Do not claim a round passed unless there is fresh evidence after the baseline.
- Do not count ADB long-press as a voice turn. The UI is click-to-record: tap once to start, tap once to send.
- Do not count a round unless the APK is foreground before the first tap and the screenshot after the round shows the APK UI, not Termux, browser, launcher, or a permission/settings screen.
- Do not treat missing Mac-side ADB forwards as backend downtime. If ADB is online but `curl :18000` fails, restore forwards first, then recheck Termux SSH and phone-local health.
- Do not commit forbidden artifacts: `frontend/dist`, `backend/data`, `backend/static/audio`, `backend/secrets`, uploaded audio, logs, screenshots, APK build outputs.
- If you write a final report, write it under `plan/V2.0/` and keep it text-only.

## Known Field Facts

- Phone: Nubia `NX531J`, serial previously `9debb82b`.
- Android: `6.0.1`, SDK `23`.
- WebView: `com.google.android.webview` `55.0.2883.91`.
- APK package: `com.petagent.shell`.
- APK WebView 55 should use frontend WAV fallback and still upload to `/api/voice/chat`.
- Browser entry must continue to work at `http://127.0.0.1:8000/`.
- Backend must run from real Termux context. SSH `id` must include `3003(inet)`.
- AppOps has previously had `RECORD_AUDIO: ignore` even while runtime permission said granted. Check both.
- Current UI voice button text is `点一下说话` when idle, `点一下发送` while recording, and may show `打断并说话` while TTS is speaking.
- The report template may contain stale values from earlier dry runs. Regenerate environment, build hash, baseline, coordinates, and counts at the start of each real run.

## Stop Conditions

Stop the run and record the reason if any condition occurs:

- `adb devices -l` does not show the Nubia as `device`.
- SSH `id` does not include `3003(inet)`.
- Backend cannot be reached from real Termux SSH context.
- `curl http://127.0.0.1:18000/api/health` fails after ADB forward recovery.
- The deployed phone build hash is not the build intended for this test run. Stop and ask the owner whether to deploy first or intentionally test the currently installed build.
- APK `RECORD_AUDIO` runtime permission is not granted and cannot be granted.
- AppOps for `com.petagent.shell RECORD_AUDIO` is `ignore` or denied and cannot be restored to `allow`.
- New APK voice turns do not reach `/api/voice/chat`.
- ASR failure creates fake success, fake reply, LLM call, or a new TTS job.
- Browser entry is broken after APK testing.
- A failure repeats for 3 consecutive rounds and basic non-disruptive recovery does not clear it.

## Files And Artifacts

- Create before testing: `plan/V2.0/voice-100-round-field-test-report.md`.
- Optional working notes: `plan/V2.0/voice-100-round-field-test-notes.md`.
- Screenshots: `/private/tmp/petagent-v20-round-001.png` through `/private/tmp/petagent-v20-round-100.png`.
- Extra failure screenshots: `/private/tmp/petagent-v20-failure-round-XXX.png`.
- Do not pull or commit raw phone logs/audio/database files. Query them over SSH and summarize results in the report.

## Task 0: Preflight

- [ ] Confirm Mac is talking to the Nubia:

```bash
adb devices -l
```

Expected: one Nubia row with state `device`.

- [ ] Restore and inspect forwards:

```bash
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
adb forward --list
```

Expected: forwards include `tcp:18000 tcp:8000` and `tcp:18022 tcp:8022`.

- [ ] Confirm real Termux context:

```bash
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
```

Expected:

- `id` contains `3003(inet)`.
- `context: ok`.
- `manager: running`.
- `manager_context: ok`.
- backend health is ok.
- SQLite quick check is ok.

- [ ] Confirm Mac verification channel:

```bash
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
```

Expected: health returns `ok=true`; build info reports the currently deployed SHA.

- [ ] Record the deployed build and intended test target:

```bash
git rev-parse --short HEAD
curl -fsS http://127.0.0.1:18000/build-info.json
curl -fsS http://127.0.0.1:18000/api/health
```

Expected: the report clearly says whether the test is running the current local build or an older deployed phone build. If this differs from the owner's intended target, stop before creating the baseline.

- [ ] Confirm APK microphone permissions:

```bash
adb shell dumpsys package com.petagent.shell | grep -E "RECORD_AUDIO|granted=true|stopped=|notLaunched"
adb shell appops get com.petagent.shell RECORD_AUDIO
```

Expected:

- `android.permission.RECORD_AUDIO: granted=true`.
- AppOps says `RECORD_AUDIO: allow`.

If runtime permission is missing, request/grant using normal Android permission flow or:

```bash
adb shell pm grant com.petagent.shell android.permission.RECORD_AUDIO
```

If AppOps is `ignore`, restore and recheck:

```bash
adb shell appops set com.petagent.shell RECORD_AUDIO allow
adb shell appops get com.petagent.shell RECORD_AUDIO
```

## Task 1: Open APK And Locate The Voice Button

- [ ] Launch APK:

```bash
adb shell monkey -p com.petagent.shell 1
```

- [ ] Take a screenshot and inspect the current UI:

```bash
adb exec-out screencap -p > /private/tmp/petagent-v20-before-voice.png
open /private/tmp/petagent-v20-before-voice.png
```

- [ ] Confirm the page is the PetAgent UI, not the native unavailable screen.
- [ ] Confirm the APK is foreground, not Termux or browser:

```bash
adb shell dumpsys window windows | grep -E "mCurrentFocus|mFocusedApp"
```

Expected: the focused package/class is `com.petagent.shell/.MainActivity` or otherwise clearly belongs to the PetAgent shell APK.

- [ ] Locate the idle voice button labeled `点一下说话`.

Use the visible button position from the screenshot. If the UI is 1080x1920 portrait and unchanged, the old practical area was near the lower center, but do not trust old coordinates blindly. The current redesigned UI can shift the button.

- [ ] Optionally inspect UI text through Android accessibility dump:

```bash
adb shell uiautomator dump /sdcard/window.xml
adb shell cat /sdcard/window.xml | grep -E "点一下说话|点一下发送|打断并说话|再试一次"
```

If the XML contains bounds for `点一下说话`, use the center of those bounds as `VOICE_BUTTON_X` and `VOICE_BUTTON_Y`.

- [ ] Record the coordinates in the report:

```text
VOICE_BUTTON_X=<number>
VOICE_BUTTON_Y=<number>
Coordinate source: screenshot or uiautomator bounds
```

## Task 2: Create Baseline

Create a baseline immediately before round 1. All proof must be newer than this baseline.

- [ ] Write a phone-side baseline JSON:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
import time
from pathlib import Path

db = Path("backend/data/pet.db")
voice_log = Path("backend/data/logs/voice_debug.jsonl")
baseline_path = Path("backend/data/logs/petagent_v20_voice_100_baseline.json")

def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as f:
        return sum(1 for _ in f)

baseline = {
    "created_at_unix": time.time(),
    "voice_debug_rows": count_lines(voice_log),
    "db_path": str(db),
}

if db.exists():
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    for table in ("raw_event_log", "agent_run", "audio_job"):
        try:
            cur.execute(f"select count(*) from {table}")
            baseline[f"{table}_count"] = cur.fetchone()[0]
        except Exception as exc:
            baseline[f"{table}_error"] = str(exc)
    conn.close()

baseline_path.parent.mkdir(parents=True, exist_ok=True)
baseline_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(baseline, ensure_ascii=False, indent=2))
PY'
```

- [ ] Copy the baseline values into `plan/V2.0/voice-100-round-field-test-report.md`.

## Task 3: Execute 100 Real Voice Rounds

Each round is a normal user-like conversation turn:

1. Tap `点一下说话` to start recording.
2. Play the round utterance from the Mac using `say`.
3. Wait a small amount so the Nubia microphone captures the whole utterance.
4. Tap the same voice button again when it says `点一下发送`.
5. Wait for response and TTS completion.
6. Capture screenshot.
7. Record visible result and backend evidence.

Do not long-press. Do not tap the cancel button. Do not count a round if the tap sequence was wrong.

Before every round, confirm the APK is still foreground. This is mandatory because previous long runs accidentally continued tapping the Termux terminal after the APK went to the background. If the APK is not foreground, relaunch it, wait for the PetAgent UI, and do not count the interrupted attempt.

```bash
adb shell dumpsys window windows | grep -E "mCurrentFocus|mFocusedApp"
```

If the focus is not `com.petagent.shell`, run:

```bash
adb shell monkey -p com.petagent.shell 1
sleep 3
```

Then recheck the screenshot and voice button bounds before continuing.

Use this command pattern per round:

```bash
VOICE_BUTTON_X=<number>
VOICE_BUTTON_Y=<number>
ROUND=001
TEXT="豆豆早上好，今天我们做一百轮语音测试，先从简单问候开始。"

adb shell input tap "$VOICE_BUTTON_X" "$VOICE_BUTTON_Y"
sleep 1
say "$TEXT"
sleep 1
adb shell input tap "$VOICE_BUTTON_X" "$VOICE_BUTTON_Y"
sleep 18
adb exec-out screencap -p > "/private/tmp/petagent-v20-round-${ROUND}.png"
test -s "/private/tmp/petagent-v20-round-${ROUND}.png"
```

Timing notes:

- Keep most recordings between 3 and 10 seconds.
- Do not exceed the frontend `MAX_RECORDING_MS=15000`.
- If TTS is still speaking after 18 seconds, wait until it finishes before the next round.
- If the button shows `打断并说话`, wait unless the scenario intentionally tests interruption.
- If the UI says `点一下发送` after `say` finishes, tap it once to send.
- If the screenshot is empty, corrupt, or shows a non-APK screen, mark the attempt invalid and do not count it as a voice round.

## Task 4: 100-Round Topic Matrix

Use natural utterances, not repeated test phrases. Keep the conversation coherent enough that context bugs can show up.

| Rounds | Dimension | Example intent |
| --- | --- | --- |
| 001-010 | Warmup and greetings | hello, simple mood check, "can you hear me" |
| 011-020 | Food and drinks | breakfast, coffee, water, dinner ideas |
| 021-030 | Weather and walks | hot/cold/rain, whether to go outside |
| 031-040 | Work and study fatigue | tired, focus, short break, encouragement |
| 041-050 | Planning tomorrow | schedule, reminders, small decisions |
| 051-060 | Emotional support | mild stress, loneliness, wanting company |
| 061-070 | Pet interaction | praise, feed, pat, play, clean room |
| 071-080 | Multi-turn memory | refer to earlier coffee/weather/work topics |
| 081-088 | Clarification and correction | "不是这个意思", "我换个说法" |
| 089-094 | Edge but normal speech | very short, longer sentence, quiet speech, background noise |
| 095-100 | Final stability | normal daily conversation and final summary request |

Suggested utterance seed list:

```text
001 豆豆早上好，今天我们做一百轮语音测试，先从简单问候开始。
002 你现在听得到我说话吗，听到的话自然回答我一下。
003 我刚刚打开了你的桌面小屋，感觉你在桌上陪着我。
004 今天你心情怎么样，想不想和我聊几句。
005 我准备连续跟你说很多轮，你不用紧张，正常聊天就行。
006 现在先问一个简单问题，你喜欢别人怎么叫你。
007 如果我说话有一点慢，你也按正常速度回应我。
008 我想确认你的声音回复能稳定播放完。
009 这一轮只是一句普通问候，豆豆你好。
010 热身结束了，我们继续聊日常。
011 我今天早上想吃面包和鸡蛋，你觉得够不够。
012 我刚喝了一杯咖啡，精神比刚才好多了。
013 如果晚上想吃清淡一点，你会推荐什么。
014 我今天水喝得有点少，你提醒我一下。
015 中午我有点想点外卖，但又怕太油。
016 如果家里只有米饭和鸡蛋，可以做点什么。
017 我想给自己买一杯奶茶，但又怕太甜。
018 今天晚饭我想简单解决，不想洗太多碗。
019 你觉得边吃饭边看视频会不会太分心。
020 食物话题先到这里，你记一下我刚才提过咖啡。
021 今天外面有点热，你觉得晚上散步合适吗。
022 如果下雨了，我们就在屋里待着聊天。
023 我喜欢傍晚凉一点的时候出去走走。
024 今天风有点大，出门可能要带外套。
025 如果天气闷，我就不跑步了，改成拉伸。
026 你的小屋里如果有窗户，你想看什么天气。
027 今天太阳很晒，我可能晚点再出门。
028 我想听你用轻松一点的语气讲讲天气。
029 如果明天下雨，你提醒我带伞。
030 天气话题结束，我们后面再看你记不记得。
031 今天工作有点累，我想休息五分钟。
032 我刚开完会，脑子有点乱。
033 如果我开始拖延，你可以温柔提醒我。
034 我想先完成一个小任务，再奖励自己休息。
035 学习的时候我容易分心，你有什么办法。
036 今天代码看久了眼睛酸。
037 我不想被催得太厉害，只想被陪一下。
038 如果我说累了，你先安慰我，不要讲大道理。
039 我准备把复杂任务拆小一点。
040 工作学习这一组结束，你可以轻轻鼓励我。
041 明天我想早点起床，但不想太痛苦。
042 我明天上午先处理最重要的一件事。
043 如果我忘了喝水，你可以在聊天里提醒我。
044 我今晚要把手机充好电。
045 明天如果天气好，我想出去走一圈。
046 我想把明天的计划控制在三件事以内。
047 你帮我想一句轻松的睡前提醒。
048 如果明天很忙，我也要记得吃饭。
049 我想给自己留一点发呆时间。
050 计划话题结束，后面我会问你记得哪些。
051 我今天有一点烦，但不是特别严重。
052 有时候我只是想有人听我说完。
053 如果我沉默一会儿，你可以安静陪着。
054 我不太想马上解决问题，只想先缓一缓。
055 你可以用短一点的话回应我。
056 我希望你的回复不要太夸张，像自然陪伴就好。
057 今天事情有点杂，我想慢慢来。
058 如果我说我没动力，你会怎么陪我。
059 我现在感觉比刚才平静一点。
060 情绪话题先停一下，我们换轻松的。
061 豆豆，我给你添一点水。
062 摸摸你的头，今天辛苦了。
063 你的小屋桌面看起来挺舒服的。
064 我给你放一个小垫子，你可以趴一会儿。
065 如果你饿了，你会怎么提醒我。
066 我想和你玩一个很短的小游戏。
067 你今天表现不错，我夸你一下。
068 如果屋子有点乱，我们一起收拾。
069 你可以做一个开心的表情吗。
070 宠物互动结束，看看你的表情有没有稳定。
071 你还记得我前面说过喝咖啡吗。
072 你还记得我说外面有点热吗。
073 我刚才说工作有点累，你现在怎么回应。
074 我们把明天计划再简单复述一下。
075 如果我晚上散步，你觉得要注意什么。
076 刚才我说不想被催太厉害，你记得吗。
077 现在把咖啡、天气、明天计划连起来聊一句。
078 我想看看你会不会把上下文弄混。
079 你不用完整总结，只要自然接上话。
080 上下文测试结束，继续普通聊天。
081 不是这个意思，我是说我想轻松一点。
082 我换个说法，今天我只是有点累。
083 刚才那句话你可以忽略，我们重新说。
084 如果你没听清，可以直接告诉我。
085 我不是要建议，只是想听你回应。
086 这轮我说得短一点，豆豆。
087 这一句稍微长一点，我想确认长句子录音识别和回复生成都还稳定，不要提前结束也不要卡住。
088 我会稍微小声一点说话，看看你能不能听清。
089 嗯。
090 好的。
091 我刚才可能说得不太清楚。
092 旁边可能有一点杂音，你按真实识别结果处理。
093 这轮如果没有听清，不要假装听清。
094 我们继续正常聊天，不需要特殊处理。
095 最后几轮了，豆豆你现在还稳定吗。
096 你用一句自然的话回应我就好。
097 今天这一百轮测试快结束了，谢谢你陪我。
098 你还记得今天聊过咖啡、天气和明天计划吗。
099 最后一轮前，我想确认你的声音能正常播放完。
100 这是第一百轮，请做一个简短自然的结束回应。
```

## Task 5: Batch Evidence Checks

Run evidence checks after rounds 10, 25, 50, 75, and 100. Also run them immediately after any suspicious failure.

- [ ] Check health:

```bash
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
curl -fsS http://127.0.0.1:18000/api/health
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

- [ ] Summarize voice records newer than the baseline:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
from pathlib import Path

base_path = Path("backend/data/logs/petagent_v20_voice_100_baseline.json")
log_path = Path("backend/data/logs/voice_debug.jsonl")
base = json.loads(base_path.read_text(encoding="utf-8"))
start = int(base.get("voice_debug_rows", 0))
rows = []
if log_path.exists():
    for i, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        if i <= start or not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            rows.append({"line": i, "parse_error": str(exc)})
            continue
        route = row.get("voice_route") or {}
        audio = row.get("audio") or {}
        rows.append({
            "line": i,
            "event": row.get("event"),
            "ok": row.get("ok"),
            "error_class": row.get("error_class"),
            "content_type": row.get("content_type"),
            "filename": row.get("filename"),
            "size_bytes": row.get("size_bytes"),
            "format": audio.get("format"),
            "duration_s": audio.get("duration_s"),
            "rms": audio.get("rms"),
            "selected": route.get("selected"),
            "thinking_mode": route.get("thinking_mode"),
            "user_text": row.get("user_text"),
        })

print(json.dumps({
    "new_voice_debug_rows": len(rows),
    "latest_10": rows[-10:],
}, ensure_ascii=False, indent=2))
PY'
```

Expected for successful APK WebView rounds:

- New row per counted round.
- New row count should match the counted round count, except explicitly documented invalid attempts that did not send audio.
- `event=voice_chat`.
- `ok=true`.
- `content_type=audio/wav`.
- `format=wav`.
- `size_bytes` non-empty and plausible.
- `duration_s` matches recording duration and stays under about 15 seconds.
- `voice_route.selected=unified`.
- `voice_route.thinking_mode=false`.
- `user_text` non-empty when ASR succeeds.

- [ ] Summarize database deltas:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
from pathlib import Path

base = json.loads(Path("backend/data/logs/petagent_v20_voice_100_baseline.json").read_text(encoding="utf-8"))
conn = sqlite3.connect("backend/data/pet.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

summary = {}
for table in ("raw_event_log", "agent_run", "audio_job"):
    cur.execute(f"select count(*) as c from {table}")
    now = cur.fetchone()["c"]
    before = int(base.get(f"{table}_count", 0))
    summary[f"{table}_delta"] = now - before

cur.execute("""
select id, event_type, source, user_text, pet_reply
from raw_event_log
where event_type='voice_message'
order by id desc
limit 10
""")
summary["latest_voice_messages"] = [dict(r) for r in cur.fetchall()]

cur.execute("""
select id, status, final_action_json, audio_job_id
from agent_run
order by id desc
limit 10
""")
summary["latest_agent_runs"] = [dict(r) for r in cur.fetchall()]

cur.execute("""
select id, status, voice_url, error_class
from audio_job
order by id desc
limit 10
""")
summary["latest_audio_jobs"] = [dict(r) for r in cur.fetchall()]

conn.close()
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY'
```

Expected for successful rounds:

- `raw_event_log_delta` increases by successful voice turns.
- Successful voice turns are `event_type=voice_message`, `source=voice_unified`.
- `user_text` and `pet_reply` are non-empty for successful turns.
- `agent_run.status=completed` for successful turns.
- Successful TTS has `audio_job.status=ready` and non-empty `voice_url`.
- `final_action_json.expression_key` should match the visible final expression. After TTS completes, the face should not fall back to a question mark unless backend actually selected that expression.

## Task 6: Failure Classification

For every non-perfect round, record:

```text
Round:
Utterance:
Screenshot:
Visible UI state:
Was a new voice_debug row created:
voice_debug ok/error_class:
ASR user_text:
raw_event_log row:
agent_run row:
audio_job row:
Likely layer:
Recovery used:
Retried as round number:
```

Use these likely layers:

- `tap_sequence`: wrong coordinate, hit cancel, hit text input, double tapped, long-pressed.
- `permission`: runtime permission or AppOps blocked mic.
- `recording`: no blob, too short, WebView recorder issue, WAV fallback issue.
- `upload`: no `/api/voice/chat` request, network timeout, backend empty reply.
- `asr_expected_failure`: explicit `ok=false` with `error_class` such as `asr_empty`.
- `asr_bad_success`: ASR failed but app generated fake success. This is a stop condition.
- `llm`: provider timeout, provider error, no fake reply.
- `tts`: `audio_job` failed, expired, no playback, retry audio shown.
- `ui_state`: stuck on thinking/listening/speaking, expression mismatch, question-mark fallback.
- `runtime`: backend, manager, SSH, database, or phone sleep issue.

Valid ASR failure behavior:

- Backend returns explicit `ok=false` and `error_class`.
- No fake assistant reply.
- No LLM call.
- No new TTS job.

Invalid ASR failure behavior:

- Empty or failed ASR still produces a fake successful answer.
- `raw_event_log` stores a successful `voice_message` without real `user_text`.
- New `audio_job` is created for an ASR failure.

## Task 7: Recovery Policy

Prefer non-disruptive checks first.

- [ ] If APK UI is stale or backgrounded, relaunch APK:

```bash
adb shell monkey -p com.petagent.shell 1
```

- [ ] If backend health from Mac fails, recheck forwarding:

```bash
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
curl -fsS http://127.0.0.1:18000/api/health
```

- [ ] If SSH/backend looks half-dead, bring Termux Activity foreground and recheck:

```bash
adb shell am start -n com.termux/.app.TermuxActivity
sleep 8
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
```

- [ ] If permission regresses:

```bash
adb shell dumpsys package com.petagent.shell | grep -E "RECORD_AUDIO|granted=true"
adb shell appops get com.petagent.shell RECORD_AUDIO
adb shell appops set com.petagent.shell RECORD_AUDIO allow
```

Do not stop the backend, clear app data, reinstall the APK, rebuild frontend, or modify code unless the owner explicitly says to do that.

## Task 8: Browser Coexistence Check

After round 100, verify the old browser entry still works.

- [ ] Open browser URL:

```bash
adb shell am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

- [ ] Take screenshot:

```bash
adb exec-out screencap -p > /private/tmp/petagent-v20-browser-after-100.png
```

- [ ] Perform one normal browser text or voice interaction.

- [ ] Confirm backend records a fresh text or voice event and the UI still uses the same served frontend, not an APK-specific fork.

## Task 9: Final Report

Write the final report to:

```text
plan/V2.0/voice-100-round-field-test-report.md
```

Required report sections:

```markdown
# V2.0 100-Round Real Voice Field Test Report

## Environment
- Date/time:
- Phone serial/model:
- Android/WebView:
- APK package:
- health build_hash:
- build-info git_sha:
- SSH id includes 3003(inet): yes/no
- RECORD_AUDIO runtime permission:
- RECORD_AUDIO AppOps:
- Voice button coordinate:

## Baseline
- baseline path:
- voice_debug_rows:
- raw_event_log_count:
- agent_run_count:
- audio_job_count:

## Summary
- attempted rounds:
- counted rounds:
- successful rounds:
- expected ASR failures:
- unexpected failures:
- stopped early: yes/no

## Batch Checks
- after 10:
- after 25:
- after 50:
- after 75:
- after 100:

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
- adb state:
- backend health:
- scripts/status.sh summary:
- manager:
- wake lock:
- Termux:Boot:
- limitations:
```

## Completion Criteria

The test is complete only if:

- 100 counted voice rounds were attempted with the real Nubia APK microphone path.
- Each counted round used ADB tap `点一下说话` -> Mac `say` -> ADB tap `点一下发送`.
- Evidence was checked from baseline-forward `voice_debug.jsonl` and SQLite.
- All failures were classified and investigated without code changes.
- Browser coexistence was verified after APK testing.
- Final report exists under `plan/V2.0/`.
- `git status --short` shows no forbidden artifacts staged or created in the repo.

Final hygiene command:

```bash
git status --short
```

Expected: only intentional text plan/report files under `plan/V2.0/`, or clean if the report is not committed.
