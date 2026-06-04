import { useEffect, useMemo, useRef, useState, type FormEvent, type MutableRefObject } from "react";

import { PetBubble } from "./components/PetBubble";
import { PetFace } from "./components/PetFace";
import { StatusBar } from "./components/StatusBar";
import { TextInputBar } from "./components/TextInputBar";
import { TouchArea } from "./components/TouchArea";
import { VoiceButton } from "./components/VoiceButton";
import {
  exitMomo,
  getAudioJob,
  getAmbientCheck,
  getInteractions,
  getPetState,
  getSiliconFlowConfig,
  getTTSConfig,
  cancelAmbientBubble,
  confirmAmbientBubble,
  postAudioRetry,
  postPetEvent,
  reportDeviceState,
  restartRuntime,
  resetRuntime,
  sendHeartbeat,
  sendTextChat,
  triggerAmbientBubble,
  updateSiliconFlowConfig,
  updateTTSConfig,
  wakeMomo
} from "./pet/api";
import { animationMap } from "./pet/animations";
import {
  buildAmbientClientState,
  getLocalDateString,
  loadAmbientState,
  resetAmbientState,
  saveAmbientState,
  shouldRequestAmbient
} from "./pet/ambient";
import { detectActivationIntent } from "./pet/activation";
import { getErrorBubble } from "./pet/errorMessages";
import { useClientConfig } from "./hooks/useClientConfig";
import { useNetworkState } from "./hooks/useNetworkState";
import type {
  ActivationResponse,
  AudioJob,
  AnimationName,
  InteractionDefinition,
  Mood,
  PetEventType,
  PetResponse,
  PetState,
  SiliconFlowConfigStatus,
  TTSConfigStatus,
  TTSMode,
  PetUIPhase,
  TextChatResponse,
  VoiceChatResponse
} from "./pet/types";

const DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1";
const TTS_MODE_ORDER: TTSMode[] = ["siliconflow", "mimo", "weilin"];
const TTS_MODE_LABELS: Record<TTSMode, string> = {
  siliconflow: "硅基流动",
  mimo: "冰糖",
  weilin: "Weilin",
};

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

function ttsModeLabel(mode: TTSMode | null | undefined): string {
  if (!mode) return "";
  return TTS_MODE_LABELS[mode] ?? mode;
}

function availableTTSModes(status: TTSConfigStatus): TTSMode[] {
  const configuredModes = new Set<TTSMode>();
  for (const option of status.options) {
    if (option.configured && TTS_MODE_ORDER.includes(option.mode)) {
      configuredModes.add(option.mode);
    }
  }
  if (configuredModes.size === 0) {
    return [...TTS_MODE_ORDER];
  }
  return TTS_MODE_ORDER.filter((mode) => configuredModes.has(mode));
}

function nextTTSMode(status: TTSConfigStatus): TTSMode | null {
  const modes = availableTTSModes(status);
  if (modes.length === 0) return null;
  const currentIndex = modes.indexOf(status.mode);
  if (modes.length === 1 && currentIndex === 0) return null;
  if (currentIndex < 0) return modes[0];
  return modes[(currentIndex + 1) % modes.length];
}

function App() {
  const [petState, setPetState] = useState<PetState>(fallbackState);
  const [faceType, setFaceType] = useState<Mood>("idle");
  const [expressionKey, setExpressionKey] = useState<string>("idle_soft");
  const [animation, setAnimation] = useState<AnimationName>("breathing");
  const [bubbleText, setBubbleText] = useState("我在这里。");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<PetUIPhase>("idle");
  const [inputActive, setInputActive] = useState(false);
  const [recordingActive, setRecordingActive] = useState(false);
  const initialAmbient = useMemo(
    () => loadAmbientState(window.localStorage, getLocalDateString()),
    [],
  );
  const [idleAnchorAt, setIdleAnchorAt] = useState(initialAmbient?.idleAnchorAt ?? Date.now());
  const [idleStep, setIdleStep] = useState(initialAmbient?.idleStep ?? 0);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [interactions, setInteractions] = useState<InteractionDefinition[]>([]);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [lastAudioJobId, setLastAudioJobId] = useState<string | null>(null);
  const [apiDialogOpen, setApiDialogOpen] = useState(false);
  const [apiConfigLoading, setApiConfigLoading] = useState(false);
  const [apiConfigSaving, setApiConfigSaving] = useState(false);
  const [apiConfigError, setApiConfigError] = useState("");
  const [apiConfigStatus, setApiConfigStatus] = useState<SiliconFlowConfigStatus | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiBaseUrlInput, setApiBaseUrlInput] = useState(DEFAULT_SILICONFLOW_BASE_URL);
  const [ttsConfigStatus, setTtsConfigStatus] = useState<TTSConfigStatus | null>(null);
  const [ttsConfigLoading, setTtsConfigLoading] = useState(false);
  const [ttsConfigSaving, setTtsConfigSaving] = useState(false);
  const [runtimeRestarting, setRuntimeRestarting] = useState(false);
  const audioRunRef = useRef(0);
  const phaseRef = useRef<PetUIPhase>("idle");
  const busyRef = useRef(false);
  const inputActiveRef = useRef(false);
  const recordingActiveRef = useRef(false);
  const idleAnchorAtRef = useRef(idleAnchorAt);
  const idleStepRef = useRef(idleStep);
  const ambientInFlightRef = useRef(false);
  const pendingAmbientEventRef = useRef<string | null>(null);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentPlaybackRef = useRef<PlaybackController | null>(null);
  const latestResponseFaceRef = useRef<{
    faceType: Mood;
    expressionKey: string;
    animation: AnimationName;
  }>({
    faceType: "idle",
    expressionKey: "idle_soft",
    animation: "breathing",
  });
  const clientConfig = useClientConfig();
  const { isOnline } = useNetworkState();

  function setPetPhase(nextPhase: PetUIPhase) {
    phaseRef.current = nextPhase;
    setPhase(nextPhase);
  }

  function setBusyState(nextBusy: boolean) {
    busyRef.current = nextBusy;
    setBusy(nextBusy);
  }

  function setInputActiveState(active: boolean) {
    inputActiveRef.current = active;
    setInputActive(active);
    if (active) cancelPendingAmbientDisplay();
  }

  function setRecordingActiveState(active: boolean) {
    recordingActiveRef.current = active;
    setRecordingActive(active);
    if (active) cancelPendingAmbientDisplay();
  }

  function applyFaceState(faceType: Mood, expressionKey: string, animation: AnimationName) {
    latestResponseFaceRef.current = { faceType, expressionKey, animation };
    setFaceType(faceType);
    setExpressionKey(expressionKey);
    setAnimation(animation);
  }

  function restoreLatestResponseFace() {
    const latest = latestResponseFaceRef.current;
    setFaceType(latest.faceType);
    setExpressionKey(latest.expressionKey);
    setAnimation(latest.animation);
  }

  function markIdleAnchor(resetStep = true) {
    const now = Date.now();
    const localDate = getLocalDateString();
    const nextStep = resetStep ? 0 : idleStepRef.current;
    idleAnchorAtRef.current = now;
    idleStepRef.current = nextStep;
    setIdleAnchorAt(now);
    setIdleStep(nextStep);
    saveAmbientState(window.localStorage, {
      idleAnchorAt: now,
      idleStep: nextStep,
      localDate,
    });
  }

  function advanceAmbientStep() {
    const now = Date.now();
    const nextStep = idleStepRef.current + 1;
    const localDate = getLocalDateString();
    idleAnchorAtRef.current = now;
    idleStepRef.current = nextStep;
    setIdleAnchorAt(now);
    setIdleStep(nextStep);
    saveAmbientState(window.localStorage, {
      idleAnchorAt: now,
      idleStep: nextStep,
      localDate,
    });
  }

  function cancelPendingAmbientDisplay() {
    const eventId = pendingAmbientEventRef.current;
    if (!eventId) return;
    pendingAmbientEventRef.current = null;
    void cancelAmbientBubble({ event_id: eventId }).catch(() => undefined);
  }

  function isAmbientDisplayStillVisible() {
    return (
      document.visibilityState === "visible" &&
      phaseRef.current === "idle" &&
      !busyRef.current &&
      !inputActiveRef.current &&
      !recordingActiveRef.current
    );
  }

  useEffect(() => {
    let alive = true;
    getPetState()
      .then((state) => {
        if (!alive) return;
        setPetState(state);
        applyFaceState(state.mood, state.mood, animationMap[state.mood] ?? "breathing");
      })
      .catch(() => {
        if (!alive) return;
        setBubbleText("我先用本地状态陪你。");
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
    if (!isOnline) return;
    const timer = window.setInterval(() => {
      if (ambientInFlightRef.current) return;
      const now = Date.now();
      const visible = document.visibilityState === "visible";
      const currentPhase = phaseRef.current;
      const currentBusy = busyRef.current;
      const currentInput = inputActiveRef.current;
      const currentRecording = recordingActiveRef.current;
      const commonState = {
        visible,
        foreground: visible,
        screenOn: visible,
        phase: currentPhase,
        busy: currentBusy,
        inputActive: currentInput,
        recording: currentRecording,
        waitingLlm: currentPhase === "thinking",
        waitingTts: currentPhase === "waiting_voice",
        playingTts: currentPhase === "speaking",
      };
      if (!shouldRequestAmbient({
        now,
        idleAnchorAt: idleAnchorAtRef.current,
        idleStep: idleStepRef.current,
        ...commonState,
      })) {
        return;
      }

      ambientInFlightRef.current = true;
      const payload = {
        local_date: getLocalDateString(),
        scene: "post_conversation_idle",
        idle_step: idleStepRef.current,
        idle_elapsed_ms: now - idleAnchorAtRef.current,
        client_state: buildAmbientClientState(commonState),
      };
      void getAmbientCheck(payload)
        .then((check) => {
          if (!check.eligible) return null;
          return triggerAmbientBubble(payload);
        })
        .then((ambient) => {
          if (!ambient?.active || !ambient.bubble) return;
          if (!isAmbientDisplayStillVisible()) {
            if (ambient.event_id) void cancelAmbientBubble({ event_id: ambient.event_id }).catch(() => undefined);
            return;
          }
          setBubbleText(ambient.bubble);
          setExpressionKey(ambient.expression_key ?? "idle_soft");
          if (ambient.event_id) {
            pendingAmbientEventRef.current = ambient.event_id;
            if (!isAmbientDisplayStillVisible()) {
              pendingAmbientEventRef.current = null;
              void cancelAmbientBubble({ event_id: ambient.event_id }).catch(() => undefined);
              markIdleAnchor(false);
              return;
            }
            void confirmAmbientBubble({ event_id: ambient.event_id })
              .then((result) => {
                if (pendingAmbientEventRef.current === ambient.event_id) {
                  pendingAmbientEventRef.current = null;
                }
                if (result.ok) {
                  advanceAmbientStep();
                } else {
                  markIdleAnchor(false);
                }
              })
              .catch(() => {
                if (pendingAmbientEventRef.current === ambient.event_id) {
                  pendingAmbientEventRef.current = null;
                }
                markIdleAnchor(false);
              });
          } else {
            markIdleAnchor(false);
          }
        })
        .catch(() => undefined)
        .finally(() => {
          ambientInFlightRef.current = false;
        });
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [isOnline]);

  useEffect(() => {
    if (!isOnline) return;
    void sendHeartbeat().catch(() => undefined);
    const timer = window.setInterval(() => {
      if (!isOnline) return;
      void sendHeartbeat().catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [isOnline]);

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

  async function handlePetEvent(interaction: InteractionDefinition) {
    markIdleAnchor(true);
    cancelPendingAmbientDisplay();
    const event = interaction.event_id;
    const preview = interactionPreview[event] ?? {
      mood: "thinking" as Mood,
      animation: "blink" as AnimationName,
      text: "我收到啦。"
    };
    setFaceType(preview.mood);
    setExpressionKey(preview.mood);
    setAnimation(preview.animation);
    setBubbleText(preview.text);

    setBusyState(true);

    try {
      const response = await postPetEvent(event);
      applyPetResponse(response);
      vibrate(response.vibration);
    } catch {
      setFaceType("concerned");
      setExpressionKey("concerned");
      setAnimation("tilt");
      setBubbleText("我刚刚没接稳，但还在这儿。");
      markIdleAnchor(true);
    } finally {
      setBusyState(false);
    }
  }

  function applyPetResponse(response: PetResponse) {
    setPetState(response.pet_state);
    applyFaceState(
      response.face_type,
      response.expression_key ?? response.face_type ?? response.mood,
      response.animation,
    );
    setBubbleText(response.reply);

    const hasAudio = !!(response.audio_job_id || response.voice_url);
    if (hasAudio) {
      setBubbleText("我准备开口…");
      setBusyState(true);
    }
    playResponseAudio(response);
    vibrate(response.vibration);
    if (!hasAudio) {
      markIdleAnchor(true);
    }
  }

  async function playResponseAudio(response: PetResponse) {
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;
    stopCurrentAudioPlayback();

    try {
      if (response.audio_job_id) {
        setLastAudioJobId(response.audio_job_id);
        setPetPhase("waiting_voice");
        const job = await waitForReadyAudio(response.audio_job_id, runId);
        if (audioRunRef.current !== runId) return;
        if (job.voice_url) {
          setLastAudioJobId(null);
          setPetPhase("speaking");
          setBubbleText("我在说…");
          await playVoice(job.voice_url, currentAudioRef, currentPlaybackRef);
          if (audioRunRef.current === runId) {
            setPetPhase("idle");
            restoreLatestResponseFace();
            setBubbleText("我说完啦。");
            markIdleAnchor(true);
          }
          return;
        }
        throw audioJobError(job);
      }

      if (response.voice_url) {
        setPetPhase("speaking");
        setBubbleText("我在说…");
        await playVoice(response.voice_url, currentAudioRef, currentPlaybackRef);
        if (audioRunRef.current === runId) {
          setPetPhase("idle");
          restoreLatestResponseFace();
          setBubbleText("我说完啦。");
          markIdleAnchor(true);
        }
        return;
      }

      setPetPhase("idle");
      restoreLatestResponseFace();
      markIdleAnchor(true);
    } catch (error) {
      if (audioRunRef.current !== runId) return;
      const errBubble = getErrorBubble(errorClassForAudioError(error));
      setPetPhase("audio_error");
      setFaceType(errBubble.mood);
      setExpressionKey(errBubble.mood);
      setAnimation("tilt");
      setBubbleText(errBubble.text);
      window.setTimeout(() => {
        if (audioRunRef.current !== runId) return;
        setPetPhase("idle");
        markIdleAnchor(true);
      }, 1500);
    } finally {
      if (audioRunRef.current === runId) {
        setBusyState(false);
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
          setBubbleText(progressive[String(thresholds[i])] ?? "我准备声音…");
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
    markIdleAnchor(true);
    cancelPendingAmbientDisplay();
    setBusyState(true);
    setPetPhase("waiting_voice");
    setBubbleText("我再试试…");
    const runId = audioRunRef.current + 1;
    audioRunRef.current = runId;
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
        setBubbleText("我在说…");
        await playVoice(job.voice_url, currentAudioRef, currentPlaybackRef);
        if (audioRunRef.current === runId) {
          setPetPhase("idle");
          restoreLatestResponseFace();
          setBubbleText("我说完啦。");
          markIdleAnchor(true);
        }
      } else {
        const errBubble = getErrorBubble(job.error_class);
        setPetPhase("audio_error");
        setFaceType(errBubble.mood);
        setExpressionKey(errBubble.mood);
        setBubbleText(errBubble.text);
        setLastAudioJobId(null);
      }
    } catch (error) {
      if (audioRunRef.current !== runId) return;
      const errBubble = getErrorBubble(errorClassForAudioError(error));
      setPetPhase("audio_error");
      setFaceType(errBubble.mood);
      setExpressionKey(errBubble.mood);
      setAnimation("tilt");
      setBubbleText(errBubble.text);
      if (error instanceof AudioJobError && error.status === "superseded") {
        setLastAudioJobId(null);
      }
    } finally {
      if (audioRunRef.current === runId) {
        setBusyState(false);
      }
    }
  }

  async function handleVoiceResponse(response: VoiceChatResponse) {
    if (response.error_class) {
      const errBubble = getErrorBubble(response.error_class);
      setFaceType(errBubble.mood);
      setExpressionKey(errBubble.mood);
      setAnimation("slowBlink");
      setBubbleText(errBubble.text);
      markIdleAnchor(true);
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
    if (nextPhase === "listening" || nextPhase === "thinking") {
      markIdleAnchor(true);
      cancelPendingAmbientDisplay();
    }
    setPetPhase(nextPhase);
    setRecordingActiveState(nextPhase === "listening" || nextPhase === "thinking");

    if (nextPhase === "listening") {
      setFaceType("thinking");
      setExpressionKey("thinking");
      setAnimation("blink");
      setBubbleText("嗯嗯，我听着呢。");
    } else if (nextPhase === "thinking") {
      setFaceType("thinking");
      setExpressionKey("thinking");
      setAnimation("blink");
      setBubbleText("我想一下…");
    } else if (nextPhase === "waiting_voice") {
      setBubbleText("我准备开口…");
    } else if (nextPhase === "audio_error") {
      setFaceType("concerned");
      setExpressionKey("concerned");
      setAnimation("tilt");
      setBubbleText("声音刚刚没出来。");
      markIdleAnchor(true);
    } else if (nextPhase === "error") {
      setFaceType("concerned");
      setExpressionKey("concerned");
      setAnimation("tilt");
      markIdleAnchor(true);
    } else if (nextPhase === "idle") {
      markIdleAnchor(true);
    }
  }

  function interruptVoiceRun() {
    audioRunRef.current += 1;
    stopCurrentAudioPlayback();
    setBusyState(false);
    setRecordingActiveState(false);
    setLastAudioJobId(null);
    markIdleAnchor(true);
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

  async function handleResetRuntime() {
    if (busy) return;
    markIdleAnchor(true);
    cancelPendingAmbientDisplay();
    const confirmed = window.confirm(
      "豆豆会忘掉之前的记忆，并回到初始状态。确定要重新认识吗？"
    );
    if (!confirmed) return;
    setBusyState(true);
    let resetSucceeded = false;
    try {
      const response = await resetRuntime();
      resetSucceeded = true;
      resetAmbientState(window.localStorage);
      audioRunRef.current += 1;
      stopCurrentAudioPlayback();
      const now = Date.now();
      idleAnchorAtRef.current = now;
      idleStepRef.current = 0;
      setIdleAnchorAt(now);
      setIdleStep(0);
      pendingAmbientEventRef.current = null;
      ambientInFlightRef.current = false;
      setPetState(response.pet_state);
      setBubbleText(response.reply);
      applyFaceState("idle", "idle_soft", "breathing");
      setPetPhase("idle");
      setLastAudioJobId(null);
      setRecordingActiveState(false);
      setInputActiveState(false);
      setActiveSession(null);
    } catch {
      setBubbleText("重新认识的时候出了点小状况。");
    } finally {
      setBusyState(false);
      if (!resetSucceeded) {
        markIdleAnchor(true);
      }
    }
  }

  async function openApiConfigDialog() {
    if (apiConfigLoading || apiConfigSaving) return;
    setApiDialogOpen(true);
    setApiConfigError("");
    setApiKeyInput("");
    setApiConfigLoading(true);
    try {
      const status = await getSiliconFlowConfig();
      setApiConfigStatus(status);
      setApiBaseUrlInput(status.base_url || DEFAULT_SILICONFLOW_BASE_URL);
    } catch {
      setApiConfigStatus(null);
      setApiBaseUrlInput(DEFAULT_SILICONFLOW_BASE_URL);
      setApiConfigError("读取当前 API 配置失败。");
    } finally {
      setApiConfigLoading(false);
    }
  }

  function closeApiConfigDialog() {
    if (apiConfigSaving) return;
    setApiDialogOpen(false);
    setApiConfigError("");
    setApiKeyInput("");
  }

  async function handleApiConfigSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (apiConfigSaving) return;
    const apiKey = apiKeyInput.trim();
    const baseUrl = apiBaseUrlInput.trim() || DEFAULT_SILICONFLOW_BASE_URL;
    if (apiKey.length < 12) {
      setApiConfigError("API Key 太短。");
      return;
    }
    if (!baseUrl.startsWith("https://")) {
      setApiConfigError("Base URL 必须是 HTTPS。");
      return;
    }

    setApiConfigSaving(true);
    setApiConfigError("");
    try {
      const status = await updateSiliconFlowConfig({
        api_key: apiKey,
        base_url: baseUrl,
      });
      setApiConfigStatus(status);
      setApiBaseUrlInput(status.base_url || baseUrl);
      setApiKeyInput("");
      setApiDialogOpen(false);
      setBubbleText("API 已更新。");
      markIdleAnchor(true);
    } catch {
      setApiConfigError("API 保存失败，请检查 Key 或网络。");
    } finally {
      setApiConfigSaving(false);
    }
  }

  async function handleToggleTTSConfig() {
    if (ttsConfigLoading || ttsConfigSaving) return;
    setTtsConfigLoading(true);
    try {
      const current = ttsConfigStatus ?? (await getTTSConfig());
      setTtsConfigStatus(current);
      const nextMode = nextTTSMode(current);
      if (!nextMode) {
        setBubbleText("现在只有一种语气可用。");
        markIdleAnchor(true);
        return;
      }
      setTtsConfigLoading(false);
      setTtsConfigSaving(true);
      const next = await updateTTSConfig({ mode: nextMode });
      setTtsConfigStatus(next);
      setBubbleText(`语气已切到${ttsModeLabel(next.mode)}。`);
      markIdleAnchor(true);
    } catch {
      setBubbleText("语气切换失败，先检查接口配置。");
      markIdleAnchor(true);
    } finally {
      setTtsConfigLoading(false);
      setTtsConfigSaving(false);
    }
  }

  async function handleRestartRuntime() {
    if (runtimeRestarting) return;
    const confirmed = window.confirm("后端会短暂断开并自动恢复。确定重启吗？");
    if (!confirmed) return;
    markIdleAnchor(true);
    cancelPendingAmbientDisplay();
    setRuntimeRestarting(true);
    setBubbleText("我去重启一下后端…");
    try {
      await restartRuntime();
      setBubbleText("后端正在重启，等我几秒。");
    } catch {
      setBubbleText("重启请求没发出去，可以稍后再试。");
    } finally {
      window.setTimeout(() => {
        setRuntimeRestarting(false);
      }, 8000);
    }
  }

  async function handleTextSubmit(text: string): Promise<boolean> {
    if (busy) return false;
    markIdleAnchor(true);
    cancelPendingAmbientDisplay();
    setBusyState(true);
    setFaceType("thinking");
    setExpressionKey("thinking");
    setAnimation("blink");
    setBubbleText("我想一下…");
    try {
      const response: TextChatResponse = await sendTextChat(text);
      if (response.activation) {
        setActiveSession(response.activation.active ? response.activation.session_id : null);
      }
      if (response.error_class) {
        const errBubble = getErrorBubble(response.error_class);
        setFaceType(errBubble.mood);
        setExpressionKey(errBubble.mood);
        setAnimation("slowBlink");
        setBubbleText(errBubble.text);
        setBusyState(false);
        markIdleAnchor(true);
        return false;
      }
      applyPetResponse(response);
      return true;
    } catch {
      setFaceType("concerned");
      setExpressionKey("concerned");
      setAnimation("tilt");
      setBubbleText("文字没发出去，再试一次？");
      markIdleAnchor(true);
      return false;
    } finally {
      setBusyState(false);
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
      <div className="top-panel">
        <StatusBar state={petState} />
      </div>
      <section className="pet-stage" aria-label={`豆豆当前心情 ${titleMood}`}>
        <div className="pet-stage-room" aria-hidden="true">
          <span className="room-shelf" />
          <span className="room-dot room-dot-left" />
          <span className="room-dot room-dot-right" />
        </div>
        <PetFace faceType={faceType} animation={animation} expressionKey={expressionKey} />
        <PetBubble text={bubbleText} busy={busy} />
      </section>
      <div className="control-deck" aria-label="豆豆互动控制">
        <VoiceButton
          disabled={isVoiceDisabled}
          phase={phase}
          onError={(message) => setBubbleText(message)}
          onInterrupt={interruptVoiceRun}
          onPhaseChange={handleVoicePhase}
          onVoiceResponse={handleVoiceResponse}
        />
        <TextInputBar
          disabled={isTextDisabled}
          onSubmit={handleTextSubmit}
          onActiveChange={setInputActiveState}
        />
        <button
          className="more-toggle-btn"
          type="button"
          onClick={() => setShowMoreMenu(!showMoreMenu)}
          aria-expanded={showMoreMenu}
        >
          {showMoreMenu ? "收起互动" : "更多互动"}
        </button>
        {showMoreMenu && (
          <div className="interaction-drawer">
            <TouchArea
              disabled={isTextDisabled || interactions.length === 0}
              interactions={interactions}
              onPetEvent={handlePetEvent}
            />
          </div>
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
          className="reset-btn"
          disabled={busy}
          onClick={handleResetRuntime}
        >
          重新认识
        </button>
        <button
          className="api-config-btn"
          disabled={apiConfigLoading || apiConfigSaving}
          onClick={openApiConfigDialog}
        >
          更换 API
        </button>
        <button
          className="runtime-restart-btn"
          disabled={runtimeRestarting}
          onClick={handleRestartRuntime}
        >
          {runtimeRestarting ? "重启中" : "重启后端"}
        </button>
        <button
          className="tts-toggle-btn"
          disabled={ttsConfigLoading || ttsConfigSaving}
          onClick={handleToggleTTSConfig}
        >
          {ttsConfigSaving || ttsConfigLoading
            ? "语气: 切换中"
            : ttsConfigStatus
              ? `语气: ${ttsModeLabel(ttsConfigStatus.mode)}`
              : "切换语气"}
        </button>
      </div>
      {apiDialogOpen && (
        <div
          className="api-config-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeApiConfigDialog();
          }}
        >
          <div
            aria-labelledby="api-config-title"
            aria-modal="true"
            className="api-config-dialog"
            role="dialog"
          >
            <h2 id="api-config-title">更换 SiliconFlow API</h2>
            <form className="api-config-form" onSubmit={handleApiConfigSubmit}>
              <label htmlFor="api-key-input">API Key</label>
              <input
                autoComplete="off"
                disabled={apiConfigSaving}
                id="api-key-input"
                onChange={(event) => setApiKeyInput(event.target.value)}
                placeholder="输入新的 API Key"
                type="password"
                value={apiKeyInput}
              />
              <label htmlFor="api-base-url-input">Base URL</label>
              <input
                autoComplete="off"
                disabled={apiConfigSaving}
                id="api-base-url-input"
                onChange={(event) => setApiBaseUrlInput(event.target.value)}
                type="text"
                value={apiBaseUrlInput}
              />
              <div className="api-config-status" role="status">
                {apiConfigLoading
                  ? "读取中…"
                  : apiConfigStatus?.api_key_configured
                    ? "当前已配置"
                    : "当前未配置"}
              </div>
              {apiConfigError && (
                <div className="api-config-error" role="alert">
                  {apiConfigError}
                </div>
              )}
              <div className="api-config-actions">
                <button
                  className="api-config-cancel"
                  disabled={apiConfigSaving}
                  onClick={closeApiConfigDialog}
                  type="button"
                >
                  取消
                </button>
                <button
                  className="api-config-save"
                  disabled={apiConfigLoading || apiConfigSaving}
                  type="submit"
                >
                  {apiConfigSaving ? "保存中…" : "保存"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
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
