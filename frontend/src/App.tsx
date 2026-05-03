import { useEffect, useMemo, useState } from "react";

import { PetBubble } from "./components/PetBubble";
import { PetFace } from "./components/PetFace";
import { StatusBar } from "./components/StatusBar";
import { TouchArea } from "./components/TouchArea";
import { getPetState, postPetEvent } from "./pet/api";
import { animationMap } from "./pet/animations";
import type { AnimationName, Mood, PetEventType, PetState } from "./pet/types";

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

  return (
    <main className="app-shell">
      <StatusBar state={petState} />
      <section className="pet-stage" aria-label={`Momo 当前心情 ${titleMood}`}>
        <h1>Momo</h1>
        <PetFace faceType={faceType} animation={animation} />
        <PetBubble text={bubbleText} busy={busy} />
      </section>
      <TouchArea disabled={busy} onPetEvent={handlePetEvent} />
    </main>
  );
}

function playVoice(voiceUrl: string | null) {
  if (!voiceUrl) return;
  const audio = new Audio(voiceUrl);
  void audio.play().catch(() => undefined);
}

function vibrate(vibration: "none" | "light" | "medium") {
  if (!("vibrate" in navigator) || vibration === "none") return;
  const pattern = vibration === "light" ? 18 : 36;
  navigator.vibrate(pattern);
}

export default App;
