import { describe, expect, test, vi } from "vitest";

import { getProactiveEvent, reportDeviceState, uploadVoice } from "./api";

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

  test("fetches proactive event endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ active: false })
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await getProactiveEvent();

    expect(fetchMock).toHaveBeenCalledWith("/api/pet/proactive", undefined);
    expect(response).toEqual({ active: false });
  });
});
