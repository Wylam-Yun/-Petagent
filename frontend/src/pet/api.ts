import type {
  ActivationResponse,
  DeviceStatePayload,
  PetEventType,
  ProactiveResponse,
  PetResponse,
  PetState,
  VoiceChatResponse
} from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getPetState(): Promise<PetState> {
  return requestJson<PetState>("/api/pet/state");
}

export function reportDeviceState(payload: DeviceStatePayload): Promise<DeviceStatePayload> {
  return requestJson<DeviceStatePayload>("/api/device/state", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function getProactiveEvent(): Promise<ProactiveResponse> {
  return requestJson<ProactiveResponse>("/api/pet/proactive");
}

export function postPetEvent(event: PetEventType): Promise<PetResponse> {
  return requestJson<PetResponse>("/api/pet/event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      event,
      payload: { description: eventDescription(event) }
    })
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

function eventDescription(event: PetEventType): string {
  switch (event) {
    case "pet_head":
      return "用户摸了你的头";
    case "poke_face":
      return "用户轻轻戳了你的脸";
    case "hug":
      return "用户抱了抱你";
    case "debug_happy":
      return "调试：开心";
    case "debug_sleepy":
      return "调试：困了";
    case "debug_angry":
      return "调试：小生气";
    default:
      return "用户和你互动";
  }
}

function extensionForType(type: string): string {
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("mp4")) return "mp4";
  return "webm";
}
