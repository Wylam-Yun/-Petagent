import type {
  AudioJob,
  DeviceStatePayload,
  InteractionDefinition,
  PetEventType,
  PetResponse,
  PetState,
  TextChatResponse,
  VoiceChatResponse
} from "./types";

export const VOICE_UPLOAD_TIMEOUT_MS = {
  fast: 30_000,
  thinking: 60_000
} as const;

async function requestJson<T>(
  url: string,
  init?: RequestInit,
  options: { timeoutMs?: number; signal?: AbortSignal } = {}
): Promise<T> {
  const maxRetries = 2;
  const timeoutMs = options.timeoutMs ?? 8_000;
  let lastError: Error | undefined;

  const method = (init?.method ?? "GET").toUpperCase();
  const canRetry = method === "GET";

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      if (!canRetry) break;
      await new Promise((r) => window.setTimeout(r, 1000 * Math.pow(2, attempt - 1)));
    }
    try {
      const response = await requestWithTransport(url, init, timeoutMs, options.signal);
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return response.json() as Promise<T>;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt === maxRetries || !canRetry) throw lastError;
    }
  }
  throw lastError ?? new Error("request failed");
}

type JsonTransportResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

function requestWithTransport(
  url: string,
  init: RequestInit | undefined,
  timeoutMs: number,
  signal?: AbortSignal
): Promise<JsonTransportResponse> {
  if (typeof fetch === "function") {
    return requestWithFetch(url, init, timeoutMs, signal);
  }
  return requestWithXhr(url, init, timeoutMs, signal);
}

async function requestWithFetch(
  url: string,
  init: RequestInit | undefined,
  timeoutMs: number,
  signal?: AbortSignal
): Promise<JsonTransportResponse> {
  const controller = createAbortController();
  let timedOut = false;
  let timer: number | null = null;
  const abortFromCaller = () => controller?.abort();
  const timeout = new Promise<never>((_, reject) => {
    timer = window.setTimeout(() => {
      timedOut = true;
      controller?.abort();
      reject(new Error("request timeout"));
    }, timeoutMs);
  });
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  try {
    return await Promise.race([
      fetch(url, {
        ...init,
        ...(controller ? { signal: controller.signal } : {})
      }),
      timeout
    ]);
  } catch (err) {
    if (signal?.aborted) throw new Error("request aborted");
    if (timedOut) throw new Error("request timeout");
    throw err;
  } finally {
    if (timer !== null) window.clearTimeout(timer);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

function requestWithXhr(
  url: string,
  init: RequestInit | undefined,
  timeoutMs: number,
  signal?: AbortSignal
): Promise<JsonTransportResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const finish = (fn: () => void) => {
      signal?.removeEventListener("abort", abortFromCaller);
      fn();
    };
    const abortFromCaller = () => xhr.abort();
    xhr.open(init?.method ?? "GET", url, true);
    xhr.timeout = timeoutMs;

    for (const [name, value] of normalizedHeaders(init?.headers)) {
      xhr.setRequestHeader(name, value);
    }

    xhr.onreadystatechange = () => {
      if (xhr.readyState !== XMLHttpRequest.DONE) return;
      finish(() => resolve({
        ok: xhr.status >= 200 && xhr.status < 300,
        status: xhr.status,
        json: async () => JSON.parse(xhr.responseText || "null")
      }));
    };
    xhr.onerror = () => finish(() => reject(new TypeError("network error")));
    xhr.ontimeout = () => finish(() => reject(new Error("request timeout")));
    xhr.onabort = () => finish(() => reject(new Error("request aborted")));
    signal?.addEventListener("abort", abortFromCaller, { once: true });
    xhr.send((init?.body as XMLHttpRequestBodyInit | null | undefined) ?? null);
    if (signal?.aborted) xhr.abort();
  });
}

function normalizedHeaders(headers: HeadersInit | undefined): [string, string][] {
  if (!headers) return [];
  if (typeof Headers !== "undefined" && headers instanceof Headers) {
    const result: [string, string][] = [];
    headers.forEach((value, name) => result.push([name, value]));
    return result;
  }
  if (Array.isArray(headers)) {
    return headers.map(([name, value]) => [name, value]);
  }
  const plainHeaders = headers as Record<string, string>;
  return Object.keys(plainHeaders).map((name) => [name, String(plainHeaders[name])]);
}

function createAbortController(): AbortController | null {
  if (typeof AbortController === "undefined") return null;
  return new AbortController();
}

export function getPetState(): Promise<PetState> {
  return requestJson<PetState>("/api/pet/state");
}

export function getAudioJob(jobId: string): Promise<AudioJob> {
  return requestJson<AudioJob>(`/api/audio/jobs/${encodeURIComponent(jobId)}`);
}

export function postAudioRetry(jobId: string): Promise<{ new_job_id: string }> {
  return requestJson<{ new_job_id: string }>(`/api/audio/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
    headers: { "content-type": "application/json" }
  });
}

export function reportDeviceState(payload: DeviceStatePayload): Promise<DeviceStatePayload> {
  return requestJson<DeviceStatePayload>("/api/device/state", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
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
  signal?: AbortSignal;
};

export function uploadVoice(
  blob: Blob,
  options: UploadVoiceOptions = {}
): Promise<VoiceChatResponse> {
  const formData = new FormData();
  formData.append("file", blob, `voice.${extensionForType(blob.type)}`);
  formData.append("thinking_mode", options.thinkingMode ? "true" : "false");
  return requestJson<VoiceChatResponse>(
    "/api/voice/chat",
    {
      method: "POST",
      body: formData
    },
    {
      timeoutMs: options.thinkingMode ? VOICE_UPLOAD_TIMEOUT_MS.thinking : VOICE_UPLOAD_TIMEOUT_MS.fast,
      signal: options.signal
    }
  );
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
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user_agent: navigator.userAgent ?? "" })
  });
}

function extensionForType(type: string): string {
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("mp4")) return "mp4";
  return "webm";
}
