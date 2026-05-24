import { Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  MicrophonePermissionError,
  RecordingTooShortError,
  createVoiceRecordingSession,
  type VoiceRecordingSession
} from "../pet/audio";
import { uploadVoice as defaultUploadVoice } from "../pet/api";
import type { PetUIPhase, VoiceChatResponse } from "../pet/types";
import type { UploadVoiceOptions } from "../pet/api";

type VoiceButtonProps = {
  disabled: boolean;
  phase: PetUIPhase;
  thinkingMode?: boolean;
  pressToRecordDelayMs?: number;
  recorderFactory?: () => Promise<VoiceRecordingSession>;
  uploadVoice?: (blob: Blob, options?: UploadVoiceOptions) => Promise<VoiceChatResponse>;
  onPhaseChange: (phase: PetUIPhase) => void;
  onVoiceResponse: (response: VoiceChatResponse) => void;
  onError: (message: string) => void;
};

const DEFAULT_PRESS_TO_RECORD_DELAY_MS = 240;

export function VoiceButton({
  disabled,
  phase,
  thinkingMode = false,
  pressToRecordDelayMs = DEFAULT_PRESS_TO_RECORD_DELAY_MS,
  recorderFactory = createVoiceRecordingSession,
  uploadVoice = defaultUploadVoice,
  onPhaseChange,
  onVoiceResponse,
  onError
}: VoiceButtonProps) {
  const [busy, setBusy] = useState(false);
  const [localPhase, setLocalPhase] = useState<PetUIPhase>(phase);
  const sessionRef = useRef<VoiceRecordingSession | null>(null);
  const armTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!busy) {
      setLocalPhase(phase);
    }
  }, [busy, phase]);

  const effectivePhase = localPhase;
  const label = labelForPhase(effectivePhase);
  const isBlocked = disabled || busy || armTimerRef.current !== null;

  useEffect(() => {
    return () => {
      clearArmTimer();
      sessionRef.current?.cancel();
    };
  }, []);

  function armRecording() {
    if (isBlocked || sessionRef.current) return;
    if (pressToRecordDelayMs <= 0) {
      void startRecording();
      return;
    }
    armTimerRef.current = window.setTimeout(() => {
      armTimerRef.current = null;
      void startRecording();
    }, pressToRecordDelayMs);
  }

  async function startRecording() {
    if (isBlocked || sessionRef.current) return;
    setBusy(true);
    try {
      sessionRef.current = await recorderFactory();
      changePhase("listening");
    } catch (error) {
      sessionRef.current = null;
      setBusy(false);
      changePhase("error");
      onError(messageForMicrophoneError(error));
    }
  }

  async function stopRecordingAndUpload() {
    if (clearArmTimer()) {
      onError("按住久一点，豆豆才听得到。");
      return;
    }
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    changePhase("thinking");
    try {
      const blob = await session.stop();
      const response = await uploadVoice(blob, { thinkingMode });
      onVoiceResponse(response);
      const fallbackReason = response.voice_route?.fallback_reason;
      if (fallbackReason === "asr_empty" || fallbackReason === "asr_low_confidence") {
        onError("豆豆没太听清，再说一次？");
      } else if (fallbackReason === "asr_timeout") {
        onError("语音识别有点慢，再说一次？");
      } else if (fallbackReason === "asr_provider_error" || fallbackReason === "asr_provider_exception") {
        onError("语音识别暂时不太灵，但豆豆还在听。");
      }
      changePhase(response.audio_job_id || response.voice_url ? "waiting_voice" : "idle");
    } catch (error) {
      changePhase("error");
      if (error instanceof RecordingTooShortError) {
        onError("豆豆刚刚只听到一点点。");
      } else if (error instanceof TypeError || (error instanceof Error && error.message.includes("fetch"))) {
        onError("网络好像有点慢，再试一次？");
      } else {
        onError("呜，刚刚没接住。");
      }
    } finally {
      setBusy(false);
    }
  }

  function cancelRecording() {
    clearArmTimer();
    sessionRef.current?.cancel();
    sessionRef.current = null;
    setBusy(false);
    changePhase("idle");
  }

  function changePhase(nextPhase: PetUIPhase) {
    setLocalPhase(nextPhase);
    onPhaseChange(nextPhase);
  }

  function clearArmTimer(): boolean {
    if (armTimerRef.current === null) return false;
    window.clearTimeout(armTimerRef.current);
    armTimerRef.current = null;
    return true;
  }

  return (
    <button
      aria-label={label}
      className={`voice-button voice-${effectivePhase}`}
      disabled={disabled}
      type="button"
      onMouseDown={armRecording}
      onMouseLeave={stopRecordingAndUpload}
      onMouseUp={stopRecordingAndUpload}
      onTouchCancel={cancelRecording}
      onTouchEnd={stopRecordingAndUpload}
      onTouchStart={(event) => {
        event.preventDefault();
        armRecording();
      }}
    >
      {effectivePhase === "error" ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
      <span>{label}</span>
    </button>
  );
}

function labelForPhase(phase: PetUIPhase): string {
  switch (phase) {
    case "listening":
      return "松开回应";
    case "thinking":
      return "让我想想";
    case "waiting_voice":
      return "准备开口";
    case "speaking":
      return "豆豆在说";
    case "audio_error":
      return "声音没出来";
    case "error":
      return "再试一次";
    default:
      return "长按说话";
  }
}

function messageForMicrophoneError(error: unknown): string {
  if (error instanceof MicrophonePermissionError) {
    if (error.reason === "insecure_context") {
      return "麦克风需要用 127.0.0.1 或 HTTPS 打开。";
    }
    if (error.reason === "missing_api") {
      return "这个浏览器叫不到麦克风，换 Chrome 或 127.0.0.1 试试。";
    }
  }
  return "呜，麦克风好像没醒。";
}
