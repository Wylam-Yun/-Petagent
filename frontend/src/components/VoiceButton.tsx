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
import type { UploadVoiceOptions } from "../pet/api";

type VoiceButtonProps = {
  disabled: boolean;
  phase: PetUIPhase;
  thinkingMode?: boolean;
  pressToRecordDelayMs?: number;
  recorderFactory?: () => Promise<VoiceRecordingSession>;
  uploadVoice?: (blob: Blob, options?: UploadVoiceOptions) => Promise<VoiceChatResponse>;
  onInterrupt?: () => void;
  onPhaseChange: (phase: PetUIPhase) => void;
  onVoiceResponse: (response: VoiceChatResponse) => void;
  onError: (message: string) => void;
};

export function VoiceButton({
  disabled,
  phase,
  thinkingMode = false,
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
  const activeUploadRunRef = useRef(0);
  const mountedRef = useRef(true);

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
      mountedRef.current = false;
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
    activeUploadRunRef.current = uploadRun;
    setBusy(true);
    try {
      const blob = await session.stop();
      const response = await uploadVoice(blob, { thinkingMode });
      if (uploadRunRef.current !== uploadRun) return;
      onVoiceResponse(response);
      const fallbackReason = response.voice_route?.fallback_reason;
      if (fallbackReason === "asr_timeout") {
        onError("语音识别有点慢，再说一次？");
      } else if (fallbackReason === "asr_provider_error" || fallbackReason === "asr_provider_exception") {
        onError("语音识别暂时不太灵，但豆豆还在听。");
      }
      changePhase(response.audio_job_id || response.voice_url ? "waiting_voice" : "idle");
    } catch (error) {
      if (uploadRunRef.current !== uploadRun) return;
      changePhase("error");
      if (error instanceof RecordingTooShortError) {
        onError("豆豆刚刚只听到一点点。");
      } else if (error instanceof Error && (error.message.includes("timeout") || error.message.includes("aborted"))) {
        onError("豆豆还在路上卡住了，再点一下试试。");
      } else if (error instanceof TypeError || (error instanceof Error && error.message.includes("fetch"))) {
        onError("网络好像有点慢，再试一次？");
      } else {
        onError("呜，刚刚没接住。");
      }
    } finally {
      if (activeUploadRunRef.current === uploadRun) {
        activeUploadRunRef.current = 0;
      }
      if (mountedRef.current) {
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
        disabled={disabled || starting || (busy && effectivePhase !== "thinking")}
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
