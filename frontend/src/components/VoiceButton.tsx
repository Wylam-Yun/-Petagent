import { Mic, MicOff, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  MicrophonePermissionError,
  RecordingTooShortError,
  createVoiceRecordingSession,
  type VoiceRecordingSession
} from "../pet/audio";
import { uploadVoice as defaultUploadVoice } from "../pet/api";
import type { PetUIPhase, VoiceChatResponse } from "../pet/types";

type VoiceButtonProps = {
  disabled: boolean;
  phase: PetUIPhase;
  pressToRecordDelayMs?: number;
  recorderFactory?: () => Promise<VoiceRecordingSession>;
  uploadVoice?: (blob: Blob) => Promise<VoiceChatResponse>;
  onInterrupt?: () => void;
  onPhaseChange: (phase: PetUIPhase) => void;
  onVoiceResponse: (response: VoiceChatResponse) => void;
  onError: (message: string) => void;
};

export function VoiceButton({
  disabled,
  phase,
  recorderFactory = createVoiceRecordingSession,
  uploadVoice = defaultUploadVoice,
  onInterrupt,
  onPhaseChange,
  onVoiceResponse,
  onError
}: VoiceButtonProps) {
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [localPhase, setLocalPhase] = useState<PetUIPhase>(phase);
  const sessionRef = useRef<VoiceRecordingSession | null>(null);
  const uploadRunRef = useRef(0);

  useEffect(() => {
    if (!busy) {
      setLocalPhase(phase);
    }
  }, [busy, phase]);

  const effectivePhase = localPhase;
  const label = labelForPhase(effectivePhase);
  const isBlocked = disabled || starting;

  useEffect(() => {
    return () => {
      uploadRunRef.current += 1;
      sessionRef.current?.cancel();
    };
  }, []);

  function handleTap() {
    if (disabled || starting) return;
    if (sessionRef.current || effectivePhase === "listening") {
      void stopRecordingAndUpload();
      return;
    }
    if (busy || effectivePhase === "thinking") {
      cancelPendingUpload();
      return;
    }
    if (effectivePhase === "waiting_voice" || effectivePhase === "speaking" || effectivePhase === "audio_error") {
      onInterrupt?.();
    }
    void startRecording();
  }

  async function startRecording() {
    if (isBlocked || sessionRef.current) return;
    setStarting(true);
    try {
      sessionRef.current = await recorderFactory();
      changePhase("listening");
    } catch (error) {
      sessionRef.current = null;
      changePhase("error");
      onError(messageForMicrophoneError(error));
    } finally {
      setStarting(false);
    }
  }

  async function stopRecordingAndUpload() {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    changePhase("thinking");
    const uploadRun = uploadRunRef.current + 1;
    uploadRunRef.current = uploadRun;
    setBusy(true);
    try {
      const blob = await session.stop();
      const response = await uploadVoice(blob);
      if (uploadRunRef.current !== uploadRun) return;
      if (response.ok === false || response.error_class) {
        onError(messageForVoiceFailure(response.error_class ?? response.voice_route?.fallback_reason));
        changePhase("error");
        return;
      }
      onVoiceResponse(response);
      changePhase(response.audio_job_id || response.voice_url ? "waiting_voice" : "idle");
    } catch (error) {
      if (uploadRunRef.current !== uploadRun) return;
      changePhase("error");
      if (error instanceof RecordingTooShortError) {
        onError("我刚刚只听到一点点。");
      } else if (error instanceof Error && (error.message.includes("timeout") || error.message.includes("aborted"))) {
        onError("我还在路上卡住了，再点一下试试。");
      } else if (error instanceof TypeError || (error instanceof Error && error.message.includes("fetch"))) {
        onError("网络好像有点慢，再试一次？");
      } else {
        onError("呜，刚刚没接住。");
      }
    } finally {
      if (uploadRunRef.current === uploadRun) {
        setBusy(false);
      }
    }
  }

  function cancelRecording() {
    sessionRef.current?.cancel();
    sessionRef.current = null;
    setBusy(false);
    changePhase("idle");
  }

  function cancelPendingUpload() {
    uploadRunRef.current += 1;
    setBusy(false);
    changePhase("idle");
  }

  function changePhase(nextPhase: PetUIPhase) {
    setLocalPhase(nextPhase);
    onPhaseChange(nextPhase);
  }

  return (
    <div className="voice-control">
      <button
        aria-label={label}
        className={`voice-button voice-${effectivePhase}`}
        disabled={disabled || starting}
        type="button"
        onClick={handleTap}
      >
        {effectivePhase === "error" ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
        <span>{label}</span>
      </button>
      {effectivePhase === "listening" && (
        <button
          aria-label="取消录音"
          className="voice-cancel-button"
          disabled={disabled}
          type="button"
          onClick={cancelRecording}
        >
          <X aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function messageForVoiceFailure(errorClass?: string | null): string {
  if (errorClass === "asr_empty" || errorClass === "asr_low_confidence") {
    return "没识别到有效语音。";
  }
  if (errorClass === "asr_timeout") {
    return "语音识别超时。";
  }
  if (errorClass?.startsWith("asr_")) {
    return "语音识别失败。";
  }
  return "语音这次失败了。";
}

function labelForPhase(phase: PetUIPhase): string {
  switch (phase) {
    case "listening":
      return "点一下发送";
    case "thinking":
      return "取消发送";
    case "waiting_voice":
      return "打断并说话";
    case "speaking":
      return "打断并说话";
    case "audio_error":
      return "点一下重说";
    case "error":
      return "再试一次";
    default:
      return "点一下说话";
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
