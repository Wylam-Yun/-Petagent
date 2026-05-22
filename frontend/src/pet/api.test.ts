import { describe, expect, test, vi } from "vitest";

import { getAudioJob, getProactiveCheck, reportDeviceState, sendTextChat, uploadVoice } from "./api";

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
