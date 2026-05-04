import { describe, expect, test, vi } from "vitest";

import { uploadVoice } from "./api";

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
