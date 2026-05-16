import { Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
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
  recorderFactory?: () => Promise<VoiceRecordingSession>;
  uploadVoice?: (blob: Blob, options?: UploadVoiceOptions) => Promise<VoiceChatResponse>;
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
  onPhaseChange,
  onVoiceResponse,
  onError
}: VoiceButtonProps) {
  const [busy, setBusy] = useState(false);
  const [localPhase, setLocalPhase] = useState<PetUIPhase>(phase);
  const sessionRef = useRef<VoiceRecordingSession | null>(null);

  useEffect(() => {
    if (!busy) {
      setLocalPhase(phase);
    }
  }, [busy, phase]);

  const effectivePhase = localPhase;
  const label = labelForPhase(effectivePhase);
  const isBlocked = disabled || busy;

  async function startRecording() {
    if (isBlocked || sessionRef.current) return;
    setBusy(true);
    try {
      sessionRef.current = await recorderFactory();
      changePhase("listening");
    } catch {
      sessionRef.current = null;
      setBusy(false);
      changePhase("error");
      onError("呜，麦克风好像没醒。");
    }
  }

  async function stopRecordingAndUpload() {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    changePhase("thinking");
    try {
      const blob = await session.stop();
      const response = await uploadVoice(blob, { thinkingMode });
      onVoiceResponse(response);
      changePhase(response.audio_job_id || response.voice_url ? "waiting_voice" : "idle");
    } catch (error) {
      changePhase("error");
      onError(
        error instanceof RecordingTooShortError
          ? "Momo 刚刚只听到一点点。"
          : "呜，刚刚没接住。"
      );
    } finally {
      setBusy(false);
    }
  }

  function cancelRecording() {
    sessionRef.current?.cancel();
    sessionRef.current = null;
    setBusy(false);
    changePhase("idle");
  }

  function changePhase(nextPhase: PetUIPhase) {
    setLocalPhase(nextPhase);
    onPhaseChange(nextPhase);
  }

  return (
    <button
      aria-label={label}
      className={`voice-button voice-${effectivePhase}`}
      disabled={disabled}
      type="button"
      onMouseDown={startRecording}
      onMouseLeave={stopRecordingAndUpload}
      onMouseUp={stopRecordingAndUpload}
      onTouchCancel={cancelRecording}
      onTouchEnd={stopRecordingAndUpload}
      onTouchStart={(event) => {
        event.preventDefault();
        void startRecording();
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
      return "Momo 在说";
    case "audio_error":
      return "声音没出来";
    case "error":
      return "再试一次";
    default:
      return "按住说话";
  }
}
