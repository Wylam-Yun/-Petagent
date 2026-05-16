import type {
  ActivationResponse,
  AudioJob,
  DeviceStatePayload,
  PetEventType,
  ProactiveResponse,
  PetResponse,
  PetState,
  TextChatResponse,
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

export function getProactiveEvent(): Promise<ProactiveResponse> {
  return requestJson<ProactiveResponse>("/api/pet/proactive");
}

export function postPetEvent(event: PetEventType): Promise<PetResponse> {
  return requestJson<PetResponse>("/api/pet/event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      event,
      payload: {
        description: eventDescription(event),
        interaction_group: interactionGroup(event)
      }
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

function eventDescription(event: PetEventType): string {
  switch (event) {
    case "pet_head":
      return "用户摸了你的头";
    case "poke_face":
      return "用户轻轻戳了你的脸";
    case "hug":
      return "用户抱了抱你";
    case "pet_pat":
      return "用户轻轻拍拍你，像是在鼓励你";
    case "praise_momo":
      return "用户夸夸了 Momo";
    case "feed_momo":
      return "用户投喂了 Momo";
    case "stay_with_me":
      return "用户希望你陪自己一下";
    case "comfort_me":
      return "用户希望你安慰自己";
    case "encourage_me":
      return "用户希望你鼓励自己";
    case "listen_to_me":
      return "用户希望你听自己吐槽";
    case "tuck_in":
      return "用户想哄你休息";
    case "clean_face":
      return "用户帮你擦擦脸";
    case "quiet_company":
      return "用户希望你安静陪着";
    case "take_a_break":
      return "用户希望你休息会儿";
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

function interactionGroup(event: PetEventType): string {
  if (["pet_head", "poke_face", "hug", "pet_pat", "praise_momo", "feed_momo", "tuck_in", "clean_face"].includes(event)) {
    return "pet_care";
  }
  if (["stay_with_me", "comfort_me", "encourage_me", "listen_to_me", "quiet_company", "take_a_break"].includes(event)) {
    return "emotional_companion";
  }
  return "debug";
}

function extensionForType(type: string): string {
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("mp4")) return "mp4";
  return "webm";
}
