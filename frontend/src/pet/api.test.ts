import { afterEach, describe, expect, test, vi } from "vitest";

import {
  VOICE_UPLOAD_TIMEOUT_MS,
  cancelAmbientBubble,
  confirmAmbientBubble,
  getAudioJob,
  getAmbientCheck,
  getClientConfig,
  getSiliconFlowConfig,
  getTTSConfig,
  postAudioRetry,
  reportDeviceState,
  restartRuntime,
  sendHeartbeat,
  sendTextChat,
  triggerAmbientBubble,
  updateSiliconFlowConfig,
  updateTTSConfig,
  uploadVoice
} from "./api";
import { getErrorBubble } from "./errorMessages";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("uploadVoice", () => {
  test("does not send thinking mode in multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true })
    });
    vi.stubGlobal("fetch", fetchMock);

    await uploadVoice(new Blob(["voice"], { type: "audio/wav" }), {
      thinkingMode: true
    });

    const [, init] = fetchMock.mock.calls[0];
    const body = init.body as FormData;
    expect(init.method).toBe("POST");
    expect(body.has("thinking_mode")).toBe(false);
  });

  test("uses a longer timeout for voice uploads than normal requests", async () => {
    const originalSetTimeout = window.setTimeout;
    const timeouts: number[] = [];
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true })
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "setTimeout").mockImplementation(((handler: TimerHandler, timeout?: number) => {
      timeouts.push(Number(timeout));
      return originalSetTimeout(handler, 0);
    }) as typeof window.setTimeout);

    await uploadVoice(new Blob(["voice"], { type: "audio/wav" }), {
      thinkingMode: false
    });

    expect(timeouts).toContain(VOICE_UPLOAD_TIMEOUT_MS.fast);
  });

  test("ignores thinking option for voice upload timeout", async () => {
    const originalSetTimeout = window.setTimeout;
    const timeouts: number[] = [];
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true })
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "setTimeout").mockImplementation(((handler: TimerHandler, timeout?: number) => {
      timeouts.push(Number(timeout));
      return originalSetTimeout(handler, 0);
    }) as typeof window.setTimeout);

    await uploadVoice(new Blob(["voice"], { type: "audio/wav" }), {
      thinkingMode: true
    });

    expect(timeouts).toContain(VOICE_UPLOAD_TIMEOUT_MS.fast);
  });
});

describe("stage 3 API helpers", () => {
  test("fetches audio job endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "aud-1", status: "pending" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await getAudioJob("aud-1");

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/audio/jobs/aud-1");
  });

  test("posts audio retry endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ new_job_id: "aud-2" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(postAudioRetry("aud-1")).resolves.toEqual({ new_job_id: "aud-2" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/audio/jobs/aud-1/retry");
    expect(init.method).toBe("POST");
  });

  test("reports device state as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ battery: 64, is_charging: true })
    });
    vi.stubGlobal("fetch", fetchMock);

    await reportDeviceState({ battery: 64, is_charging: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/device/state");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      battery: 64,
      is_charging: true
    });
  });

  test("posts ambient check endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ eligible: true, block_reason: "" })
    });
    vi.stubGlobal("fetch", fetchMock);
    const payload = ambientPayload();

    await getAmbientCheck(payload);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/pet/ambient/check");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  test("posts ambient trigger and lifecycle endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true })
    });
    vi.stubGlobal("fetch", fetchMock);

    await triggerAmbientBubble(ambientPayload());
    await confirmAmbientBubble({ event_id: "ambient-1" });
    await cancelAmbientBubble({ event_id: "ambient-2" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/pet/ambient/trigger");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/pet/ambient/confirm");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/pet/ambient/cancel");
  });

  test("sends frontend heartbeat as JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, received_at: "now" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await sendHeartbeat();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/frontend/heartbeat");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toHaveProperty("user_agent");
  });

  test("fetches SiliconFlow provider config without exposing a key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        provider: "siliconflow",
        api_key_configured: true,
        base_url: "https://api.siliconflow.cn/v1"
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getSiliconFlowConfig();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/runtime/provider-config/siliconflow");
    expect(JSON.stringify(result)).not.toContain("sk-test");
    expect(result.api_key_configured).toBe(true);
  });

  test("updates SiliconFlow provider config as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        provider: "siliconflow",
        api_key_configured: true,
        base_url: "https://api.siliconflow.cn/v1"
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    await updateSiliconFlowConfig({
      api_key: "sk-new-siliconflow-key",
      base_url: "https://api.siliconflow.cn/v1"
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runtime/provider-config/siliconflow");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      api_key: "sk-new-siliconflow-key",
      base_url: "https://api.siliconflow.cn/v1"
    });
  });

  test("fetches TTS config without provider secrets", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        mode: "siliconflow",
        active_provider: "siliconflow_tts",
        options: [],
        configured: true,
        last_primary_error: null
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getTTSConfig();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/runtime/tts-config");
    expect(JSON.stringify(result)).not.toContain("sk-test");
    expect(result.mode).toBe("siliconflow");
  });

  test("updates TTS mode as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        mode: "weilin",
        active_provider: "weilin",
        options: [],
        configured: true,
        last_primary_error: null
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    await updateTTSConfig({ mode: "weilin" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runtime/tts-config");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ mode: "weilin" });
  });

  test("posts runtime restart confirmation as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        accepted: true,
        message: "PetAgent runtime restart scheduled"
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    await restartRuntime();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runtime/restart");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ confirm: "重启后端" });
  });
});

function ambientPayload() {
  return {
    local_date: "2026-05-31",
    scene: "post_conversation_idle",
    idle_step: 0,
    idle_elapsed_ms: 300000,
    client_state: {
      visible: true,
      foreground: true,
      screen_on: true,
      idle: true,
      busy: false,
      input_active: false,
      recording: false,
      waiting_llm: false,
      waiting_tts: false,
      playing_tts: false
    }
  };
}

describe("audio error copy", () => {
  test("maps playback and unknown audio errors", () => {
    expect(getErrorBubble("playback").text).toBe("声音生成了，但浏览器没播出来。");
    expect(getErrorBubble("unknown").text).toBe("声音刚刚没出来。");
  });
});

describe("sendTextChat", () => {
  test("sends text without thinking mode as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ reply: "好呀。" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await sendTextChat("帮我写两数之和", { thinkingMode: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/text/chat");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      text: "帮我写两数之和"
    });
    expect(JSON.parse(init.body as string)).not.toHaveProperty("thinking_mode");
  });
});

describe("requestJson retry", () => {
  test("does not require AbortController in old Android browsers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ active: false })
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("AbortController", undefined);

    await expect(getAudioJob("aud-1")).resolves.toEqual({ active: false });

    const [, init] = fetchMock.mock.calls[0];
    expect(init).not.toHaveProperty("signal");
  });

  test("times out fetch requests even when AbortController is missing", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => undefined));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("AbortController", undefined);

    const promise = uploadVoice(new Blob(["voice"], { type: "audio/wav" }), {
      thinkingMode: false
    });
    const assertion = expect(promise).rejects.toThrow("request timeout");
    await vi.advanceTimersByTimeAsync(VOICE_UPLOAD_TIMEOUT_MS.fast);

    await assertion;
    const [, init] = fetchMock.mock.calls[0];
    expect(init).not.toHaveProperty("signal");
  });

  test("falls back to XMLHttpRequest when fetch is missing", async () => {
    const originalFetch = globalThis.fetch;
    const originalXhr = globalThis.XMLHttpRequest;

    class FakeXMLHttpRequest {
      static DONE = 4;
      readyState = 0;
      status = 0;
      responseText = "";
      timeout = 0;
      onreadystatechange: (() => void) | null = null;
      onerror: (() => void) | null = null;
      ontimeout: (() => void) | null = null;
      onabort: (() => void) | null = null;
      headers: Record<string, string> = {};
      method = "";
      url = "";
      body: XMLHttpRequestBodyInit | null = null;

      open(method: string, url: string) {
        this.method = method;
        this.url = url;
      }

      setRequestHeader(name: string, value: string) {
        this.headers[name] = value;
      }

      send(body: XMLHttpRequestBodyInit | null) {
        this.body = body;
        this.status = 200;
        this.responseText = JSON.stringify({ active: false });
        this.readyState = FakeXMLHttpRequest.DONE;
        this.onreadystatechange?.();
      }
    }

    vi.stubGlobal("fetch", undefined);
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);

    await expect(getAudioJob("aud-1")).resolves.toEqual({ active: false });

    vi.stubGlobal("fetch", originalFetch);
    vi.stubGlobal("XMLHttpRequest", originalXhr);
  });

  test("client config uses the same transport fallback", async () => {
    const originalFetch = globalThis.fetch;
    const originalXhr = globalThis.XMLHttpRequest;

    class FakeXMLHttpRequest {
      static DONE = 4;
      readyState = 0;
      status = 0;
      responseText = "";
      timeout = 0;
      onreadystatechange: (() => void) | null = null;
      method = "";
      url = "";

      open(method: string, url: string) {
        this.method = method;
        this.url = url;
      }

      setRequestHeader() {
        return undefined;
      }

      send() {
        this.status = 200;
        this.responseText = JSON.stringify({ audio_wait_ms: 12345, pet_name: "豆豆" });
        this.readyState = FakeXMLHttpRequest.DONE;
        this.onreadystatechange?.();
      }
    }

    vi.stubGlobal("fetch", undefined);
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);

    await expect(getClientConfig()).resolves.toEqual({
      audio_wait_ms: 12345,
      pet_name: "豆豆",
    });

    vi.stubGlobal("fetch", originalFetch);
    vi.stubGlobal("XMLHttpRequest", originalXhr);
  });

  test("retries on failure and succeeds on second attempt", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ active: false })
      });
    vi.stubGlobal("fetch", fetchMock);

    const response = await getAudioJob("aud-1");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(response).toEqual({ active: false });
  });

  test("throws after max retries exhausted", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("persistent failure"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAudioJob("aud-1")).rejects.toThrow("persistent failure");
    // 1 initial + 2 retries = 3 total
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
