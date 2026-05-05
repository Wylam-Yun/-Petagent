import { useEffect, useMemo, useState } from "react";

import { PetBubble } from "./components/PetBubble";
import { PetFace } from "./components/PetFace";
import { StatusBar } from "./components/StatusBar";
import { TouchArea } from "./components/TouchArea";
import { VoiceButton } from "./components/VoiceButton";
import { VoiceModeToggle } from "./components/VoiceModeToggle";
import {
  exitMomo,
  getPetState,
  getProactiveEvent,
  postPetEvent,
  refreshContext,
  reportDeviceState,
  wakeMomo
} from "./pet/api";
import { animationMap } from "./pet/animations";
import { detectActivationIntent } from "./pet/activation";
import { shouldApplyProactive } from "./pet/proactive";
import type {
  ActivationResponse,
  AnimationName,
  Mood,
  PetEventType,
  PetResponse,
  PetState,
  PetUIPhase,
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

const optimistic: Record<PetEventType, { mood: Mood; animation: AnimationName; text: string }> = {
  pet_head: { mood: "shy", animation: "wiggle", text: "嘿嘿…" },
  poke_face: { mood: "angry", animation: "shake", text: "唔？" },
  hug: { mood: "happy", animation: "bounce", text: "Momo 贴过来啦。" },
  debug_happy: { mood: "happy", animation: "bounce", text: "开心模式。" },
  debug_sleepy: { mood: "sleepy", animation: "slowBlink", text: "有点困困的。" },
  debug_angry: { mood: "angry", animation: "shake", text: "小小生气一下。" }
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
      void getProactiveEvent()
        .then((response) => {
          if (!response.active || !shouldApplyProactive({ phase, busy })) return;
          applyPetResponse(response);
        })
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [phase, busy]);

  const titleMood = useMemo(() => petState.mood, [petState.mood]);

  async function handlePetEvent(event: PetEventType) {
    const preview = optimistic[event];
    setFaceType(preview.mood);
    setAnimation(preview.animation);
    setBubbleText(preview.text);
    setBusy(true);

    try {
      const response = await postPetEvent(event);
      setPetState(response.pet_state);
      setFaceType(response.face_type);
      setAnimation(response.animation);
      setBubbleText(response.reply);
      playVoice(response.voice_url);
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
    setBubbleText(response.reply);
    playVoice(response.voice_url, () => setPhase("idle"));
    vibrate(response.vibration);
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

  return (
    <main className={`app-shell ${activeSession ? "is-active-session" : ""}`}>
      <StatusBar state={petState} />
      <section className="pet-stage" aria-label={`Momo 当前心情 ${titleMood}`}>
        <h1>Momo</h1>
        <PetFace faceType={faceType} animation={animation} />
        <PetBubble text={bubbleText} busy={busy} />
      </section>
      <div className="control-deck">
        <VoiceModeToggle thinkingMode={thinkingMode} onChange={setThinkingMode} />
        <VoiceButton
          disabled={busy}
          phase={phase}
          thinkingMode={thinkingMode}
          onError={(message) => setBubbleText(message)}
          onPhaseChange={handleVoicePhase}
          onVoiceResponse={handleVoiceResponse}
        />
        <TouchArea disabled={busy || phase === "thinking"} onPetEvent={handlePetEvent} />
      </div>
      <div className="secondary-actions">
        <button
          className="context-refresh-btn"
          disabled={busy}
          onClick={handleRefreshContext}
        >
          换个话题
        </button>
      </div>
    </main>
  );
}

function playVoice(voiceUrl: string | null, onEnded?: () => void) {
  if (!voiceUrl) return;
  const audio = new Audio(voiceUrl);
  audio.onended = () => onEnded?.();
  void audio.play().catch(() => undefined);
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
