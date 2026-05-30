import { afterEach, describe, expect, test, vi } from "vitest";

import {
  VOICE_UPLOAD_TIMEOUT_MS,
  getAudioJob,
  getProactiveCheck,
  postAudioRetry,
  reportDeviceState,
  sendHeartbeat,
  sendTextChat,
  uploadVoice
} from "./api";
import { getErrorBubble } from "./errorMessages";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("uploadVoice", () => {
  test("sends thinking mode as multipart form data", async () => {
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
    expect(body.get("thinking_mode")).toBe("true");
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

  test("uses a full-chain timeout for thinking voice uploads", async () => {
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

    expect(timeouts).toContain(VOICE_UPLOAD_TIMEOUT_MS.thinking);
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

  test("fetches proactive check endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ active: false })
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await getProactiveCheck();

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/pet/proactive");
    expect(response).toEqual({ active: false });
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
});

describe("audio error copy", () => {
  test("maps playback and unknown audio errors", () => {
    expect(getErrorBubble("playback").text).toBe("声音生成了，但浏览器没播出来。");
    expect(getErrorBubble("unknown").text).toBe("声音刚刚没出来。");
  });
});

describe("sendTextChat", () => {
  test("sends text and thinking mode as JSON", async () => {
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
      text: "帮我写两数之和",
      thinking_mode: true
    });
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

    await expect(getProactiveCheck()).resolves.toEqual({ active: false });

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

    await expect(getProactiveCheck()).resolves.toEqual({ active: false });

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

    const response = await getProactiveCheck();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(response).toEqual({ active: false });
  });

  test("throws after max retries exhausted", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("persistent failure"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getProactiveCheck()).rejects.toThrow("persistent failure");
    // 1 initial + 2 retries = 3 total
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
