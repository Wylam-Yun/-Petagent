import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";

import { DoudouSprite } from "./components/DoudouSprite";
import { PetBubble } from "./components/PetBubble";
import { StatusBar } from "./components/StatusBar";
import { TextInputBar } from "./components/TextInputBar";
import { TouchArea } from "./components/TouchArea";
import { VoiceButton } from "./components/VoiceButton";
import { VoiceModeToggle } from "./components/VoiceModeToggle";
import {
  getAudioJob,
  getInteractions,
  getPetState,
  getProactiveCheck,
  postAudioRetry,
  postPetEvent,
  refreshContext,
  reportDeviceState,
  resetRuntime,
  sendHeartbeat,
  sendTextChat,
  triggerProactiveEvent
} from "./pet/api";
import { animationMap } from "./pet/animations";
import {
  BehaviorDirector,
  FAST_ACTION_MIN_VISIBLE_MS,
} from "./pet/behaviorDirector";
import { getErrorBubble } from "./pet/errorMessages";
import { shouldApplyProactive } from "./pet/proactive";
import { useClientConfig } from "./hooks/useClientConfig";
import { useNetworkState } from "./hooks/useNetworkState";
import type { DoudouAction } from "./pet/doudouSprites";
import type {
  AudioJob,
  AnimationName,
  InteractionDefinition,
  Mood,
  PetEventType,
  PetResponse,
  PetState,
  PetUIPhase,
  TextChatResponse,
  VoiceChatResponse
} from "./pet/types";

const fallbackState: PetState = {
  schema_version: "0.1",
  name: "豆豆",
  mood: "idle",
  energy: 72,
  intimacy: 40,
  hunger: 30,
  cleanliness: 85,
  loneliness: 35,
  sleepiness: 15,
  mode: "idle"
};

class AudioJobError extends Error {
  constructor(
    message: string,
    readonly errorClass: string = "unknown",
    readonly status?: AudioJob["status"],
    readonly jobId?: string,
  ) {
    super(message);
    this.name = "AudioJobError";
  }
}

const terminalAudioStatuses = new Set<AudioJob["status"]>([
  "failed",
  "expired",
  "superseded",
  "failed_runtime_restart",
  "failed_shutdown",
]);

function App() {
  const [petState, setPetState] = useState<PetState>(fallbackState);
  const [faceType, setFaceType] = useState<Mood>("idle");
  const [animation, setAnimation] = useState<AnimationName>("breathing");
  const [doudouAction, setDoudouAction] = useState<DoudouAction>("idle");
  const [bubbleText, setBubbleText] = useState("豆豆在这里。");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<PetUIPhase>("idle");
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [interactions, setInteractions] = useState<InteractionDefinition[]>([]);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [lastAudioJobId, setLastAudioJobId] = useState<string | null>(null);
  const audioRunRef = useRef(0);
  const phaseRef = useRef<PetUIPhase>("idle");
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentPlaybackRef = useRef<PlaybackController | null>(null);
  const fastActionHoldTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const directorRef = useRef(new BehaviorDirector());
  const clientConfig = useClientConfig();
  const { isOnline } = useNetworkState();

  function setPetPhase(nextPhase: PetUIPhase) {
    phaseRef.current = nextPhase;
    setPhase(nextPhase);
  }

  const clearFastActionHoldTimer = useCallback(() => {
    if (fastActionHoldTimerRef.current) {
      window.clearTimeout(fastActionHoldTimerRef.current);
      fastActionHoldTimerRef.current = null;
    }
  }, []);

  useEffect(() => clearFastActionHoldTimer, [clearFastActionHoldTimer]);

  useEffect(() => {
    let alive = true;
    getPetState()
      .then((state) => {
        if (!alive) return;
        setPetState(state);
        setFaceType(state.mood);
        setAnimation(animationMap[state.mood] ?? "breathing");
        setDoudouAction(BehaviorDirector.phaseToAction("idle"));
      })
      .catch(() => {
        if (!alive) return;
        setBubbleText("豆豆先用本地状态陪你。");
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    getInteractions()
      .then((items) => {
        if (alive) setInteractions(Array.isArray(items) ? items : []);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let battery: BatteryManager | null = null;
    let cancelled = false;
    let reportBattery: (() => void) | null = null;

    async function attachBattery() {
      const getBattery = navigatorGetBattery();
      if (!getBattery) return;
      try {
        battery = await getBattery();
      } catch {
        return;
      }
      if (cancelled || !battery) return;
      reportBattery = () => {
        void reportDeviceState({
          battery: Math.round((battery?.level ?? 0) * 100),
          is_charging: battery?.charging ?? null
        }).catch(() => undefined);
      };
      reportBattery();
      battery.addEventListener("chargingchange", reportBattery);
      battery.addEventListener("levelchange", reportBattery);
    }

    void attachBattery();
    return () => {
      cancelled = true;
      if (!battery || !reportBattery) return;
      battery.removeEventListener("chargingchange", reportBattery);
      battery.removeEventListener("levelchange", reportBattery);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!isOnline) return;
      if (!shouldApplyProactive({ phase, busy })) return;
      void getProactiveCheck()
        .then((check) => {
          if (!check.active || !shouldApplyProactive({ phase, busy })) return;
          return triggerProactiveEvent();
        })
        .then((response) => {
          if (response && response.active) applyPetResponse(response);
        })
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [phase, busy, isOnline]);

  useEffect(() => {
    if (!isOnline) return;
    void sendHeartbeat().catch(() => undefined);
    const timer = window.setInterval(() => {
      if (!isOnline) return;
      void sendHeartbeat().catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [isOnline]);

  // Ambient life loop
  useEffect(() => {
    const timer = window.setInterval(() => {
      const out = directorRef.current.onAmbientTick(
        Date.now(),
        phase,
        busy,
        document.visibilityState === "visible",
      );
      if (out) {
        setDoudouAction(out.visibleAction);
        if (out.bubbleText) setBubbleText(out.bubbleText);
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [phase, busy]);

  const titleMood = useMemo(() => petState.mood, [petState.mood]);
  const interactionPreview = useMemo(() => {
    const result: Partial<Record<PetEventType, { mood: Mood; animation: AnimationName; text: string }>> = {};
    for (const item of interactions) {
      result[item.event_id] = {
        mood: item.default_mood,
        animation: item.default_animation,
        text: item.label + "…"
      };
    }
    return result;
  }, [interactions]);

  const handleDoudouTap = useCallback(() => {
    const out = directorRef.current.onTap(Date.now(), phase);
    setDoudouAction(out.visibleAction);
    if (out.bubbleText) setBubbleText(out.bubbleText);
  }, [phase]);

  const handleOneShotComplete = useCallback((action: DoudouAction) => {
    // Return to phase-appropriate action after one-shot
    const currentPhase = phaseRef.current;
    if (currentPhase === "listening" || currentPhase === "waiting_voice" || currentPhase === "speaking") {
      if (directorRef.current.isFastActionHoldActive()) return;
      setDoudouAction(BehaviorDirector.phaseToAction(currentPhase));
    } else {
      setDoudouAction("idle");
    }
  }, []);

  function applyPhaseAction(nextPhase: PetUIPhase) {
    const out = directorRef.current.onPhaseChange(nextPhase);
    setDoudouAction(out.visibleAction);
    return out;
  }

  function applySpeechPhaseAction(slotAction?: DoudouAction) {
    if (slotAction) {
      clearFastActionHoldTimer();
      setDoudouAction(slotAction);
    } else if (!directorRef.current.isFastActionHoldActive()) {
      setDoudouAction(BehaviorDirector.phaseToAction("speaking"));
    }
  }

  function scheduleFastActionHoldRelease(runId: number) {
    clearFastActionHoldTimer();
    fastActionHoldTimerRef.current = window.setTimeout(() => {
      fastActionHoldTimerRef.current = null;
      if (audioRunRef.current !== runId) return;
      setDoudouAction(
        BehaviorDirector.phaseToAction(
          phaseRef.current === "speaking" ? "speaking" : "waiting_voice",
        ),
      );
    }, FAST_ACTION_MIN_VISIBLE_MS);
  }

  async function handlePetEvent(interaction: InteractionDefinition) {
    const event = interaction.event_id;
    const preview = interactionPreview[event] ?? {
      mood: "thinking" as Mood,
      animation: "blink" as AnimationName,
      text: "豆豆收到啦。"
    };
    setFaceType(preview.mood);
    setAnimation(preview.animation);
    setBubbleText(preview.text);
    setDoudouAction("review");

    if (interaction.requires_model !== true) {
      return;
    }

    setBusy(true);

    try {
      const response = await postPetEvent(event);
      applyPetResponse(response);
      vibrate(response.vibration);
    } catch {
      setFaceType("concerned");
      setAnimation("tilt");
      setBubbleText("豆豆刚刚没接稳，但还在这儿。");
      setDoudouAction("failed");
    } finally {
      setBusy(false);
    }
  }

  function applyPetResponse(response: PetResponse) {
    setPetState(response.pet_state);
    setFaceType(response.face_type);
    setAnimation(response.animation);

    // Feed response to director for behavior plan
    const out = directorRef.current.onBackendResponse(
      {
        behavior_intent: response.behavior_intent,
        behavior_plan: response.behavior_plan,
        action: response.action,
        mood: response.mood,
        reply: response.reply,
      },
      phase,
      Date.now(),
    );
    setDoudouAction(out.visibleAction);
    if (out.bubbleText) setBubbleText(out.bubbleText);

    const hasAudio = !!(response.audio_job_id || response.voice_url);
    if (hasAudio) {
      setBubbleText("豆豆准备开口…");
      setBusy(true);
    }
    playResponseAudio(response);
    vibrate(response.vibration);
  }

  async function playResponseAudio(response: PetResponse) {
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;
    stopCurrentAudioPlayback();
    clearFastActionHoldTimer();

    try {
      if (response.audio_job_id) {
        setLastAudioJobId(response.audio_job_id);
        setPetPhase("waiting_voice");
        applyPhaseAction("waiting_voice");
        if (response.action) scheduleFastActionHoldRelease(runId);
        const beforeOut = directorRef.current.advanceSlot("before_speech");
        if (beforeOut) setDoudouAction(beforeOut.visibleAction);
        const job = await waitForReadyAudio(response.audio_job_id, runId);
        if (audioRunRef.current !== runId) return;
        if (job.voice_url) {
          setLastAudioJobId(null);
          setPetPhase("speaking");
          applyPhaseAction("speaking");
          setBubbleText("豆豆在说…");
          const speechOut = directorRef.current.advanceSlot("speech");
          applySpeechPhaseAction(speechOut?.visibleAction);
          await playVoice(job.voice_url, currentAudioRef, currentPlaybackRef);
          if (audioRunRef.current === runId) {
            setPetPhase("idle");
            setBubbleText("豆豆说完啦。");
            const afterOut = directorRef.current.advanceSlot("after_speech");
            setDoudouAction(afterOut?.visibleAction ?? "idle");
          }
          return;
        }
        throw audioJobError(job);
      }

      if (response.voice_url) {
        setPetPhase("speaking");
        applyPhaseAction("speaking");
        if (response.action) scheduleFastActionHoldRelease(runId);
        setBubbleText("豆豆在说…");
        const speechOut = directorRef.current.advanceSlot("speech");
        applySpeechPhaseAction(speechOut?.visibleAction);
        await playVoice(response.voice_url, currentAudioRef, currentPlaybackRef);
        if (audioRunRef.current === runId) {
          setPetPhase("idle");
          setBubbleText("豆豆说完啦。");
          const afterOut = directorRef.current.advanceSlot("after_speech");
          setDoudouAction(afterOut?.visibleAction ?? "idle");
        }
        return;
      }

      setPetPhase("idle");
    } catch (error) {
      if (audioRunRef.current !== runId) return;
      const errBubble = getErrorBubble(errorClassForAudioError(error));
      setPetPhase("audio_error");
      setFaceType(errBubble.mood);
      setAnimation("tilt");
      setBubbleText(errBubble.text);
      setDoudouAction(BehaviorDirector.phaseToAction("audio_error"));
    } finally {
      if (audioRunRef.current === runId) {
        clearFastActionHoldTimer();
      }
      if (audioRunRef.current === runId) {
        setBusy(false);
      }
    }
  }

  async function waitForReadyAudio(jobId: string, runId: number) {
    const startedAt = Date.now();
    const timeout = clientConfig.audio_wait_ms;
    const progressive = clientConfig.audio_progressive;
    const thresholds = Object.keys(progressive)
      .map(Number)
      .sort((a, b) => a - b);
    let lastThresholdIdx = -1;

    while (Date.now() - startedAt < timeout) {
      if (audioRunRef.current !== runId) {
        throw new Error("audio job superseded");
      }

      const elapsed = Date.now() - startedAt;
      for (let i = thresholds.length - 1; i >= 0; i--) {
        if (elapsed >= thresholds[i] && i > lastThresholdIdx) {
          lastThresholdIdx = i;
          setBubbleText(progressive[String(thresholds[i])] ?? "豆豆准备声音…");
          break;
        }
      }

      const job = await getAudioJob(jobId);
      if (job.status === "ready") return job;
      if (terminalAudioStatuses.has(job.status)) {
        throw audioJobError(job);
      }
      await sleep(500);
    }
    throw new AudioJobError("audio job timed out", "timeout", undefined, jobId);
  }

  async function handleRetryAudio() {
    if (!lastAudioJobId || busy) return;
    setBusy(true);
    setPetPhase("waiting_voice");
    setBubbleText("豆豆再试试…");
    applyPhaseAction("waiting_voice");
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;
    clearFastActionHoldTimer();
    try {
      const { new_job_id } = await postAudioRetry(lastAudioJobId);
      if (audioRunRef.current !== runId) return;
      setLastAudioJobId(new_job_id);
      // Poll the new job
      const job = await waitForReadyAudio(new_job_id, runId);
      if (!job || audioRunRef.current !== runId) return;
      if (job.voice_url) {
        setLastAudioJobId(null);
        setPetPhase("speaking");
        applyPhaseAction("speaking");
        setBubbleText("豆豆在说…");
        setDoudouAction(BehaviorDirector.phaseToAction("speaking"));
        await playVoice(job.voice_url, currentAudioRef, currentPlaybackRef);
        if (audioRunRef.current === runId) {
          setPetPhase("idle");
          setBubbleText("豆豆说完啦。");
          setDoudouAction("idle");
        }
      } else {
        const errBubble = getErrorBubble(job.error_class);
        setPetPhase("audio_error");
        setBubbleText(errBubble.text);
        setDoudouAction(BehaviorDirector.phaseToAction("audio_error"));
        setLastAudioJobId(null);
      }
    } catch (error) {
      if (audioRunRef.current !== runId) return;
      const errBubble = getErrorBubble(errorClassForAudioError(error));
      setPetPhase("audio_error");
      setFaceType(errBubble.mood);
      setAnimation("tilt");
      setBubbleText(errBubble.text);
      setDoudouAction(BehaviorDirector.phaseToAction("audio_error"));
      if (error instanceof AudioJobError && error.status === "superseded") {
        setLastAudioJobId(null);
      }
    } finally {
      if (audioRunRef.current === runId) {
        setBusy(false);
      }
    }
  }

  async function handleVoiceResponse(response: VoiceChatResponse) {
    if (response.error_class) {
      const errBubble = getErrorBubble(response.error_class);
      setFaceType(errBubble.mood);
      setAnimation("slowBlink");
      setBubbleText(errBubble.text);
      setDoudouAction(BehaviorDirector.phaseToAction("audio_error"));
      return;
    }

    if (response.activation) {
      setActiveSession(response.activation.active ? response.activation.session_id : null);
      applyPetResponse(response);
      return;
    }

    applyPetResponse(response);
  }

  function handleVoicePhase(nextPhase: PetUIPhase) {
    setPetPhase(nextPhase);
    const out = applyPhaseAction(nextPhase);
    setDoudouAction(out.visibleAction);

    if (nextPhase === "listening") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText("嗯嗯，豆豆听着呢。");
    } else if (nextPhase === "thinking") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText(thinkingMode ? "豆豆多想一下。" : "马上回应你。");
    } else if (nextPhase === "waiting_voice") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText("豆豆准备开口…");
    } else if (nextPhase === "audio_error") {
      setFaceType("concerned");
      setAnimation("tilt");
      setBubbleText("声音刚刚没出来。");
    } else if (nextPhase === "error") {
      setFaceType("concerned");
      setAnimation("tilt");
    }
  }

  function interruptVoiceRun() {
    audioRunRef.current += 1;
    stopCurrentAudioPlayback();
    clearFastActionHoldTimer();
    setBusy(false);
    setLastAudioJobId(null);
  }

  function stopCurrentAudioPlayback() {
    const audio = currentAudioRef.current;
    const playback = currentPlaybackRef.current;
    playback?.stop();
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      if (typeof audio.removeAttribute === "function") {
        audio.removeAttribute("src");
      }
      if (typeof audio.load === "function") {
        audio.load();
      }
    }
    currentAudioRef.current = null;
    currentPlaybackRef.current = null;
  }

  async function handleRefreshContext() {
    if (busy) return;
    setBusy(true);
    try {
      const response = await refreshContext();
      setBubbleText(response.reply);
      setFaceType("idle");
      setAnimation("breathing");
      setDoudouAction("idle");
    } catch {
      setBubbleText("换个话题的时候出了点小状况。");
    } finally {
      setBusy(false);
    }
  }

  async function handleResetRuntime() {
    if (busy) return;
    const confirmed = window.confirm(
      "豆豆会忘掉之前的记忆，并回到初始状态。确定要重新认识吗？"
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      const response = await resetRuntime();
      setPetState(response.pet_state);
      setBubbleText(response.reply);
      setFaceType("idle");
      setAnimation("breathing");
      setDoudouAction("idle");
      setActiveSession(null);
    } catch {
      setBubbleText("重新认识的时候出了点小状况。");
    } finally {
      setBusy(false);
    }
  }

  async function handleTextSubmit(text: string): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setFaceType("thinking");
    setAnimation("blink");
    setBubbleText("豆豆想一下…");
    setDoudouAction("review");
    try {
      const response: TextChatResponse = await sendTextChat(text, { thinkingMode });
      if (response.activation) {
        setActiveSession(response.activation.active ? response.activation.session_id : null);
      }
      if (response.error_class) {
        const errBubble = getErrorBubble(response.error_class);
        setFaceType(errBubble.mood);
        setAnimation("slowBlink");
        setBubbleText(errBubble.text);
        setDoudouAction("failed");
        setBusy(false);
        return false;
      }
      applyPetResponse(response);
      return true;
    } catch {
      setFaceType("concerned");
      setAnimation("tilt");
      setBubbleText("文字没发出去，再试一次？");
      setDoudouAction("failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const isTextDisabled = busy || phase === "thinking" || phase === "speaking" || phase === "waiting_voice";
  const isVoiceInterruptAllowed = phase === "waiting_voice" || phase === "speaking" || phase === "audio_error";
  const isVoiceDisabled = busy && !isVoiceInterruptAllowed;

  return (
    <main className={`app-shell ${activeSession ? "is-active-session" : ""}`}>
      {!isOnline && (
        <div className="offline-banner" role="status">
          正在重新连接豆豆…
        </div>
      )}
      <StatusBar state={petState} />
      <section className="pet-stage" aria-label={`豆豆当前心情 ${titleMood}`}>
        <h1>豆豆</h1>
        <DoudouSprite
          action={doudouAction}
          onTap={handleDoudouTap}
          onOneShotComplete={handleOneShotComplete}
        />
        <PetBubble text={bubbleText} busy={busy} />
      </section>
      <div className="control-deck">
        <TextInputBar disabled={isTextDisabled} onSubmit={handleTextSubmit} />
        <VoiceModeToggle thinkingMode={thinkingMode} onChange={setThinkingMode} />
        <VoiceButton
          disabled={isVoiceDisabled}
          phase={phase}
          thinkingMode={thinkingMode}
          onError={(message) => setBubbleText(message)}
          onInterrupt={interruptVoiceRun}
          onPhaseChange={handleVoicePhase}
          onVoiceResponse={handleVoiceResponse}
        />
        <button
          className="more-toggle-btn"
          type="button"
          onClick={() => setShowMoreMenu(!showMoreMenu)}
          aria-expanded={showMoreMenu}
        >
          {showMoreMenu ? "收起" : "更多互动"}
        </button>
        {showMoreMenu && (
          <TouchArea
            disabled={isTextDisabled || interactions.length === 0}
            interactions={interactions}
            onPetEvent={handlePetEvent}
          />
        )}
      </div>
      <div className="secondary-actions">
        {phase === "audio_error" && lastAudioJobId && (
          <button
            className="retry-audio-btn"
            disabled={busy}
            onClick={handleRetryAudio}
          >
            重试发声
          </button>
        )}
        <button
          className="context-refresh-btn"
          disabled={busy}
          onClick={handleRefreshContext}
        >
          换个话题
        </button>
        <button
          className="reset-btn"
          disabled={busy}
          onClick={handleResetRuntime}
        >
          重新认识
        </button>
      </div>
    </main>
  );
}

type PlaybackController = {
  stop: () => void;
};

function audioJobError(job: AudioJob): AudioJobError {
  return new AudioJobError(
    job.error ?? "audio job " + job.status,
    job.error_class ?? "unknown",
    job.status,
    job.job_id,
  );
}

function errorClassForAudioError(error: unknown): string {
  if (error instanceof AudioJobError) {
    return error.errorClass;
  }
  if (error instanceof Error) {
    if (error.message.includes("playback")) return "playback";
    if (error.message.includes("timed out")) return "timeout";
  }
  return "unknown";
}

function playVoice(
  voiceUrl: string,
  audioRef?: MutableRefObject<HTMLAudioElement | null>,
  playbackRef?: MutableRefObject<PlaybackController | null>,
  timeoutMs = 20_000,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const audio = new Audio(voiceUrl);
    if (audioRef) {
      audioRef.current = audio;
    }
    let settled = false;
    const timer = window.setTimeout(() => finish(false), timeoutMs);

    function finish(ok: boolean) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      audio.onended = null;
      audio.onerror = null;
      if (audioRef?.current === audio) {
        audioRef.current = null;
      }
      if (playbackRef?.current === controller) {
        playbackRef.current = null;
      }
      ok ? resolve() : reject(new Error("audio playback failed"));
    }

    const controller: PlaybackController = {
      stop: () => {
        audio.pause();
        finish(true);
      },
    };
    if (playbackRef) {
      playbackRef.current = controller;
    }

    audio.onended = () => finish(true);
    audio.onerror = () => finish(false);
    void audio.play().catch(() => finish(false));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function vibrate(vibration: "none" | "light" | "medium") {
  if (!("vibrate" in navigator) || vibration === "none") return;
  const pattern = vibration === "light" ? 18 : 36;
  navigator.vibrate(pattern);
}

export default App;

type BatteryManager = EventTarget & {
  charging: boolean;
  level: number;
};

function navigatorGetBattery(): (() => Promise<BatteryManager>) | null {
  const candidate = navigator as Navigator & {
    getBattery?: () => Promise<BatteryManager>;
  };
  return candidate.getBattery ?? null;
}
