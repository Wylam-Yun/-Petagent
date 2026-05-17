import { useEffect, useMemo, useRef, useState } from "react";

import { PetBubble } from "./components/PetBubble";
import { PetFace } from "./components/PetFace";
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
  sendTextChat,
  triggerProactiveEvent,
  wakeMomo
} from "./pet/api";
import { animationMap } from "./pet/animations";
import { detectActivationIntent } from "./pet/activation";
import { shouldApplyProactive } from "./pet/proactive";
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
  name: "Momo",
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
  const [bubbleText, setBubbleText] = useState("Momo 在这里。");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<PetUIPhase>("idle");
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [interactions, setInteractions] = useState<InteractionDefinition[]>([]);
  const audioRunRef = useRef(0);

  useEffect(() => {
    let alive = true;
    getPetState()
      .then((state) => {
        if (!alive) return;
        setPetState(state);
        setFaceType(state.mood);
        setAnimation(animationMap[state.mood] ?? "breathing");
      })
      .catch(() => {
        if (!alive) return;
        setBubbleText("Momo 先用本地状态陪你。");
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
      .catch(() => {
        if (alive) setBubbleText("Momo 的互动按钮还在加载。");
      });
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

  async function handlePetEvent(event: PetEventType) {
    const preview = interactionPreview[event] ?? {
      mood: "thinking" as Mood,
      animation: "blink" as AnimationName,
      text: "Momo 收到啦。"
    };
    setFaceType(preview.mood);
    setAnimation(preview.animation);
    setBubbleText(preview.text);
    setBusy(true);

    try {
      const response = await postPetEvent(event);
      applyPetResponse(response);
      vibrate(response.vibration);
    } catch {
      setFaceType("concerned");
      setAnimation("tilt");
      setBubbleText("Momo 刚刚没接稳，但还在这儿。");
    } finally {
      setBusy(false);
    }
  }

  function applyPetResponse(response: PetResponse) {
    setPetState(response.pet_state);
    setFaceType(response.face_type);
    setAnimation(response.animation);
    const hasAudio = !!(response.audio_job_id || response.voice_url);
    setBubbleText(hasAudio ? "Momo 准备开口…" : "Momo 刚刚没发出声。");
    if (hasAudio) setBusy(true);
    playResponseAudio(response);
    vibrate(response.vibration);
  }

  async function playResponseAudio(response: PetResponse) {
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;

    try {
      if (response.audio_job_id) {
        setPhase("waiting_voice");
        const job = await waitForReadyAudio(response.audio_job_id, runId);
        if (audioRunRef.current !== runId) return;
        if (job.voice_url) {
          setPhase("speaking");
          setBubbleText("Momo 在说…");
          await playVoice(job.voice_url);
          if (audioRunRef.current === runId) {
            setPhase("idle");
            setBubbleText("Momo 说完啦。");
          }
          return;
        }
        throw new Error(job.error ?? "audio job failed");
      }

      if (response.voice_url) {
        setPhase("speaking");
        setBubbleText("Momo 在说…");
        await playVoice(response.voice_url);
        if (audioRunRef.current === runId) {
          setPhase("idle");
          setBubbleText("Momo 说完啦。");
        }
        return;
      }

      setPhase("idle");
    } catch {
      if (audioRunRef.current !== runId) return;
      setPhase("audio_error");
      setBubbleText("声音刚刚没出来。");
      await sleep(1600);
      if (audioRunRef.current === runId) {
        setPhase("idle");
      }
    } finally {
      if (audioRunRef.current === runId) {
        setBusy(false);
      }
    }
  }

  async function waitForReadyAudio(jobId: string, runId: number) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < 15_000) {
      if (audioRunRef.current !== runId) {
        throw new Error("audio job superseded");
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

  async function handleVoiceResponse(response: VoiceChatResponse) {
    // If backend already handled wake/exit via VoicePipeline, apply directly
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
    if (nextPhase === "listening") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText("嗯嗯，Momo 听着呢。");
    } else if (nextPhase === "thinking") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText(thinkingMode ? "Momo 多想一下。" : "马上回应你。");
    } else if (nextPhase === "waiting_voice") {
      setFaceType("thinking");
      setAnimation("blink");
      setBubbleText("Momo 准备开口…");
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
    } catch {
      setBubbleText("换个话题的时候出了点小状况。");
    } finally {
      setBusy(false);
    }
  }

  async function handleResetRuntime() {
    if (busy) return;
    const confirmed = window.confirm(
      "Momo 会忘掉测试记忆，并回到初始状态。确定要重新认识吗？"
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      const response = await resetRuntime();
      setPetState(response.pet_state);
      setBubbleText(response.reply);
      setFaceType("idle");
      setAnimation("breathing");
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
    setBubbleText("Momo 想一下…");
    try {
      const response: TextChatResponse = await sendTextChat(text, { thinkingMode });
      if (response.activation) {
        setActiveSession(response.activation.active ? response.activation.session_id : null);
      }
      applyPetResponse(response);
      return true;
    } catch {
      setFaceType("concerned");
      setAnimation("tilt");
      setBubbleText("文字没发出去，再试一次？");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={`app-shell ${activeSession ? "is-active-session" : ""}`}>
      <StatusBar state={petState} />
      <section className="pet-stage" aria-label={`Momo 当前心情 ${titleMood}`}>
        <h1>Momo</h1>
        <PetFace faceType={faceType} animation={animation} />
        <PetBubble text={bubbleText} busy={busy} />
      </section>
      <div className="control-deck">
        <TextInputBar disabled={busy || phase === "thinking" || phase === "speaking" || phase === "waiting_voice"} onSubmit={handleTextSubmit} />
        <VoiceModeToggle thinkingMode={thinkingMode} onChange={setThinkingMode} />
        <VoiceButton
          disabled={busy}
          phase={phase}
          thinkingMode={thinkingMode}
          onError={(message) => setBubbleText(message)}
          onPhaseChange={handleVoicePhase}
          onVoiceResponse={handleVoiceResponse}
        />
        <TouchArea
          disabled={busy || phase === "thinking" || phase === "speaking" || phase === "waiting_voice" || interactions.length === 0}
          interactions={interactions}
          onPetEvent={handlePetEvent}
        />
      </div>
      <div className="secondary-actions">
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
