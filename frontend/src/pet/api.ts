import type {
  ActivationResponse,
  AudioJob,
  DeviceStatePayload,
  InteractionDefinition,
  PetEventType,
  ProactiveResponse,
  PetResponse,
  PetState,
  TextChatResponse,
  VoiceChatResponse
} from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const maxRetries = 2;
  const timeoutMs = 8_000;
  let lastError: Error | undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      await new Promise((r) => window.setTimeout(r, 1000 * Math.pow(2, attempt - 1)));
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { ...init, signal: controller.signal });
      window.clearTimeout(timer);
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return response.json() as Promise<T>;
    } catch (err) {
      window.clearTimeout(timer);
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt === maxRetries) throw lastError;
    }
  }
  throw lastError ?? new Error("request failed");
}

export function getPetState(): Promise<PetState> {
  return requestJson<PetState>("/api/pet/state");
}

export function getAudioJob(jobId: string): Promise<AudioJob> {
  return requestJson<AudioJob>(`/api/audio/jobs/${encodeURIComponent(jobId)}`);
}

export function reportDeviceState(payload: DeviceStatePayload): Promise<DeviceStatePayload> {
  return requestJson<DeviceStatePayload>("/api/device/state", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function getProactiveCheck(): Promise<{ active: boolean; candidate?: string }> {
  return requestJson("/api/pet/proactive");
}

export function triggerProactiveEvent(): Promise<ProactiveResponse> {
  return requestJson<ProactiveResponse>("/api/pet/proactive/trigger", {
    method: "POST",
    headers: { "content-type": "application/json" }
  });
}

export function getInteractions(): Promise<InteractionDefinition[]> {
  return requestJson<InteractionDefinition[]>("/api/interactions");
}

export function postPetEvent(event: PetEventType): Promise<PetResponse> {
  return requestJson<PetResponse>("/api/pet/event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ event, payload: {} })
  });
}

export type UploadVoiceOptions = {
  thinkingMode?: boolean;
};

export function uploadVoice(
  blob: Blob,
  options: UploadVoiceOptions = {}
): Promise<VoiceChatResponse> {
  const formData = new FormData();
  formData.append("file", blob, `voice.${extensionForType(blob.type)}`);
  formData.append("thinking_mode", options.thinkingMode ? "true" : "false");
  return requestJson<VoiceChatResponse>("/api/voice/chat", {
    method: "POST",
    body: formData
  });
}

export function wakeMomo(phrase: string, confidence: number): Promise<ActivationResponse> {
  return requestJson<ActivationResponse>("/api/activation/wake", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ phrase, confidence, source: "foreground_voice" })
  });
}

export function exitMomo(phrase: string, confidence: number): Promise<ActivationResponse> {
  return requestJson<ActivationResponse>("/api/activation/exit", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ phrase, confidence, source: "foreground_voice" })
  });
}

export type ContextRefreshResponse = {
  ok: boolean;
  episode: {
    episode_id: string;
    status: string;
    started_at_utc: string;
  };
  reply: string;
};

export function refreshContext(): Promise<ContextRefreshResponse> {
  return requestJson<ContextRefreshResponse>("/api/context/refresh", {
    method: "POST",
    headers: { "content-type": "application/json" }
  });
}

export type RuntimeResetResponse = {
  ok: boolean;
  pet_state: PetState;
  reply: string;
};

export function resetRuntime(): Promise<RuntimeResetResponse> {
  return requestJson<RuntimeResetResponse>("/api/runtime/reset", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ confirm: "重新认识" })
  });
}

export type SendTextOptions = {
  thinkingMode?: boolean;
};

export function sendTextChat(
  text: string,
  options: SendTextOptions = {}
): Promise<TextChatResponse> {
  return requestJson<TextChatResponse>("/api/text/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      text,
      thinking_mode: options.thinkingMode === true
    })
  });
}

export function sendHeartbeat(): Promise<{ ok: boolean; received_at: string }> {
  return requestJson("/api/frontend/heartbeat", {
    method: "POST",
    headers: { "content-type": "application/json" }
  });
}

function extensionForType(type: string): string {
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("mp4")) return "mp4";
  return "webm";
}
