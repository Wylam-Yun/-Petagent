import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DoudouSprite } from "./components/DoudouSprite";
import { PetBubble } from "./components/PetBubble";
import { StatusBar } from "./components/StatusBar";
import { TextInputBar } from "./components/TextInputBar";
import { TouchArea } from "./components/TouchArea";
import { VoiceButton } from "./components/VoiceButton";
import { VoiceModeToggle } from "./components/VoiceModeToggle";
import {
  exitMomo,
  getAudioJob,
  getInteractions,
  getPetState,
  getProactiveCheck,
  postPetEvent,
  refreshContext,
  reportDeviceState,
  resetRuntime,
  sendHeartbeat,
  sendTextChat,
  triggerProactiveEvent,
  wakeMomo
} from "./pet/api";
import { animationMap } from "./pet/animations";
import { BehaviorDirector } from "./pet/behaviorDirector";
import { detectActivationIntent } from "./pet/activation";
import { getErrorBubble } from "./pet/errorMessages";
import { shouldApplyProactive } from "./pet/proactive";
import { useClientConfig } from "./hooks/useClientConfig";
import { useNetworkState } from "./hooks/useNetworkState";
import type { DoudouAction } from "./pet/doudouSprites";
import type {
  ActivationResponse,
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
  const directorRef = useRef(new BehaviorDirector());
  const clientConfig = useClientConfig();
  const { isOnline } = useNetworkState();

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
    // Fire-and-forget backend sync for deliberate tap (no LLM/TTS)
    void postPetEvent("pet_head").catch(() => undefined);
  }, [phase]);

  const handleOneShotComplete = useCallback((action: DoudouAction) => {
    // Return to phase-appropriate action after one-shot
    if (phase === "listening" || phase === "waiting_voice" || phase === "speaking") {
      setDoudouAction(BehaviorDirector.phaseToAction(phase));
    } else {
      setDoudouAction("idle");
    }
  }, [phase]);

  async function handlePetEvent(event: PetEventType) {
    const preview = interactionPreview[event] ?? {
      mood: "thinking" as Mood,
      animation: "blink" as AnimationName,
      text: "豆豆收到啦。"
    };
    setFaceType(preview.mood);
    setAnimation(preview.animation);
    setBubbleText(preview.text);
    setDoudouAction("review");
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
        behavior_intent: (response as Record<string, unknown>).behavior_intent as string | undefined,
        behavior_plan: (response as Record<string, unknown>).behavior_plan,
        mood: response.mood,
        reply: response.reply,
      },
      phase,
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

    try {
      if (response.audio_job_id) {
        setLastAudioJobId(response.audio_job_id);
        setPhase("waiting_voice");
        const job = await waitForReadyAudio(response.audio_job_id, runId);
        if (audioRunRef.current !== runId) return;
        if (job.voice_url) {
          setLastAudioJobId(null);
          setPhase("speaking");
          setBubbleText("豆豆在说…");
          setDoudouAction("review");
          await playVoice(job.voice_url);
          if (audioRunRef.current === runId) {
            setPhase("idle");
            setBubbleText("豆豆说完啦。");
            setDoudouAction("idle");
          }
          return;
        }
        throw new Error(job.error ?? "audio job failed");
      }

      if (response.voice_url) {
        setPhase("speaking");
        setBubbleText("豆豆在说…");
        setDoudouAction("review");
        await playVoice(response.voice_url);
        if (audioRunRef.current === runId) {
          setPhase("idle");
          setBubbleText("豆豆说完啦。");
          setDoudouAction("idle");
        }
        return;
      }

      setPhase("idle");
    } catch {
      if (audioRunRef.current !== runId) return;
      setPhase("audio_error");
      setBubbleText("声音刚刚没出来。");
      setDoudouAction("failed");
    } finally {
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
      if (job.status === "failed" || job.status === "expired" || job.status === "superseded") {
        throw new Error(job.error ?? "audio job " + job.status);
      }
      await sleep(500);
    }
    throw new Error("audio job timed out");
  }

  async function handleRetryAudio() {
    if (!lastAudioJobId || busy) return;
    setBusy(true);
    setPhase("waiting_voice");
    setBubbleText("豆豆再试试…");
    setDoudouAction("review");
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;
    try {
      const job = await getAudioJob(lastAudioJobId);
      if (audioRunRef.current !== runId) return;
      if (job.voice_url) {
        setLastAudioJobId(null);
        setPhase("speaking");
        setBubbleText("豆豆在说…");
        setDoudouAction("review");
        await playVoice(job.voice_url);
        if (audioRunRef.current === runId) {
          setPhase("idle");
          setBubbleText("豆豆说完啦。");
          setDoudouAction("idle");
        }
      } else if (job.status === "failed" || job.status === "expired") {
        setPhase("audio_error");
        setBubbleText("声音没出来，可能需要重新说一遍。");
        setDoudouAction("failed");
        setLastAudioJobId(null);
      } else {
        setBubbleText("声音还在准备，再等一下…");
      }
    } catch {
      if (audioRunRef.current !== runId) return;
      setPhase("audio_error");
      setBubbleText("重试也失败了。");
      setDoudouAction("failed");
      setLastAudioJobId(null);
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
      setDoudouAction("failed");
      return;
    }

    if (response.activation) {
      setActiveSession(response.activation.active ? response.activation.session_id : null);
      applyPetResponse(response);
      return;
    }

    const intent = detectActivationIntent(
      response.user_text,
      response.audio_understanding.confidence
    );

    try {
      if (intent === "wake") {
        const activation = await wakeMomo(
          response.user_text,
          response.audio_understanding.confidence
        );
        setActiveSession(activation.active ? activation.session_id : null);
        applyActivationResponse(activation);
        return;
      }
      if (intent === "exit") {
        const activation = await exitMomo(
          response.user_text,
          response.audio_understanding.confidence
        );
        setActiveSession(activation.active ? activation.session_id : null);
        applyActivationResponse(activation);
        return;
      }
    } catch {
      setActiveSession(null);
    }

    applyPetResponse(response);
  }

  function applyActivationResponse(response: ActivationResponse) {
    applyPetResponse(response);
  }

  function handleVoicePhase(nextPhase: PetUIPhase) {
    setPhase(nextPhase);
    const out = directorRef.current.onPhaseChange(nextPhase);
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

  const isVoiceDisabled = busy || phase === "thinking" || phase === "speaking" || phase === "waiting_voice";

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
        <TextInputBar disabled={isVoiceDisabled} onSubmit={handleTextSubmit} />
        <VoiceModeToggle thinkingMode={thinkingMode} onChange={setThinkingMode} />
        <VoiceButton
          disabled={isVoiceDisabled}
          phase={phase}
          thinkingMode={thinkingMode}
          onError={(message) => setBubbleText(message)}
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
            disabled={isVoiceDisabled || interactions.length === 0}
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

function playVoice(voiceUrl: string, timeoutMs = 20_000): Promise<void> {
  return new Promise((resolve, reject) => {
  const audio = new Audio(voiceUrl);
    let settled = false;
    const timer = window.setTimeout(() => finish(false), timeoutMs);

    function finish(ok: boolean) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      audio.onended = null;
      audio.onerror = null;
      ok ? resolve() : reject(new Error("audio playback failed"));
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
