import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";

import App from "./App";

class MockAudio {
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  paused = false;
  loaded = false;

  constructor(readonly src: string) {}

  play() {
    window.setTimeout(() => this.onended?.(), 0);
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
  }

  removeAttribute() {
    return undefined;
  }

  load() {
    this.loaded = true;
  }
}

vi.stubGlobal("Audio", MockAudio);

const interactionCatalogResponse = [
  {
    event_id: "pet_head",
    label: "摸摸头",
    group: "pet_care",
    default_mood: "shy",
    default_animation: "wiggle",
    state_semantics: {},
    requires_model: false
  }
];

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function flush() {
  // Advance enough for fetch responses and initial renders.
  // Do NOT use runAllTimersAsync — the ambient setInterval would loop forever.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
}

test("App renders 豆豆 and shows kaomoji face", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema_version: "0.1",
        name: "豆豆",
        mood: "idle",
        energy: 72,
        intimacy: 40,
        hunger: 30,
        cleanliness: 85,
        loneliness: 35,
        sleepiness: 15,
        mode: "idle"
      })
    })
    .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await flush();

  expect(screen.getByText("豆豆")).toBeInTheDocument();
  expect(screen.getByLabelText("豆豆表情")).toHaveTextContent("(・ω・)");
});

test("local more interaction updates kaomoji without backend post", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema_version: "0.1",
        name: "豆豆",
        mood: "idle",
        energy: 72,
        intimacy: 40,
        hunger: 30,
        cleanliness: 85,
        loneliness: 35,
        sleepiness: 15,
        mode: "idle"
      })
    })
    .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await flush();

  fireEvent.click(screen.getByRole("button", { name: "更多互动" }));
  fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));

  expect(screen.getByLabelText("豆豆表情")).toHaveClass("animation-wiggle");
  expect(screen.getByText("摸摸头…")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

describe("text chat", () => {
  test("typed text sends POST and applies response", async () => {
    const petStateResponse = {
      schema_version: "0.1",
      name: "豆豆",
      mood: "idle",
      energy: 72,
      intimacy: 40,
      hunger: 30,
      cleanliness: 85,
      loneliness: 35,
      sleepiness: 15,
      mode: "idle"
    };

    const textChatResponse = {
      reply: "好呀，豆豆帮你想。",
      mood: "thinking",
      face_type: "thinking",
      animation: "tilt",
      vibration: "none",
      voice_url: null,
      audio_job_id: "aud-text",
      user_text: "帮我写两数之和",
      text_route: {
        selected: "thinking",
        thinking_mode: true,
        brain_provider: "test",
        timings_ms: {}
      },
      pet_state: { ...petStateResponse, mood: "thinking" as const },
      runtime: { event_id: "evt-text", skills_used: [] }
    };

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => petStateResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => textChatResponse })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "aud-text",
          status: "ready",
          voice_url: "/static/audio/text.wav",
          error: null,
          created_at: "now",
          updated_at: "now"
        })
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await flush();

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "帮我写两数之和" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    // Advance timers for fetch resolution, audio polling, and playback
    for (let i = 0; i < 10; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200);
      });
    }

    expect(screen.getByText("豆豆说完啦。")).toBeInTheDocument();

    const [, textInit] = fetchMock.mock.calls[4];
    expect(textInit.method).toBe("POST");
    expect(JSON.parse(textInit.body as string)).toMatchObject({
      text: "帮我写两数之和",
      thinking_mode: false
    });
  });

  test("fast reply still starts audio polling while kaomoji remains responsive", async () => {
    const petStateResponse = {
      schema_version: "0.1",
      name: "豆豆",
      mood: "idle",
      energy: 72,
      intimacy: 40,
      hunger: 30,
      cleanliness: 85,
      loneliness: 35,
      sleepiness: 15,
      mode: "idle"
    };

    const textChatResponse = {
      reply: "早呀，豆豆伸个懒腰。",
      mood: "happy",
      face_type: "happy",
      animation: "bounce",
      vibration: "none",
      voice_url: null,
      audio_job_id: "aud-fast-action",
      action: "happy",
      user_text: "早上好",
      text_route: {
        selected: "fast_reply",
        thinking_mode: false,
        brain_provider: "test",
        timings_ms: {}
      },
      pet_state: { ...petStateResponse, mood: "happy" as const },
      runtime: { event_id: "evt-text", skills_used: [] }
    };

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 2000, audio_progressive: {}, pet_name: "豆豆" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => petStateResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => textChatResponse })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: "aud-fast-action",
          status: "pending",
          voice_url: null,
          error: null,
          created_at: "now",
          updated_at: "now"
        })
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await flush();

    fireEvent.change(screen.getByPlaceholderText("输入一句话……"), { target: { value: "早上好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(screen.getByLabelText("豆豆表情")).toHaveClass("animation-bounce");
    expect(screen.getByText("豆豆准备开口…")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/audio/jobs/aud-fast-action")).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(screen.getByLabelText("豆豆表情")).toHaveClass("animation-bounce");
  });
});

test("mic tap during speaking stops current audio and starts a new recording", async () => {
  const audioInstances: MockAudio[] = [];
  const clearTimeoutSpy = vi.spyOn(window, "clearTimeout");
  class ManualAudio extends MockAudio {
    constructor(src: string) {
      super(src);
      audioInstances.push(this);
    }

    play() {
      return Promise.resolve();
    }
  }
  vi.stubGlobal("Audio", ManualAudio);

  const petStateResponse = {
    schema_version: "0.1",
    name: "豆豆",
    mood: "idle",
    energy: 72,
    intimacy: 40,
    hunger: 30,
    cleanliness: 85,
    loneliness: 35,
    sleepiness: 15,
    mode: "idle"
  };
  const textChatResponse = {
    reply: "豆豆说话中。",
    mood: "happy",
    face_type: "happy",
    animation: "bounce",
    vibration: "none",
    voice_url: null,
    audio_job_id: "aud-speaking",
    user_text: "你好",
    text_route: {
      selected: "fast_reply",
      thinking_mode: false,
      brain_provider: "test",
      timings_ms: {}
    },
    pet_state: { ...petStateResponse, mood: "happy" as const },
    runtime: { event_id: "evt-text", skills_used: [] }
  };
  const voiceResponse = {
    ...textChatResponse,
    user_text: "打断一下",
    audio_understanding: {
      user_text: "打断一下",
      detected_emotion: "calm",
      tone_notes: "",
      non_verbal: "",
      confidence: 0.9
    },
    audio_job_id: "aud-voice",
    voice_url: null
  };
  const originalMediaDevices = navigator.mediaDevices;
  const originalMediaRecorder = window.MediaRecorder;
  class FakeMediaRecorder {
    static isTypeSupported() {
      return true;
    }

    state = "inactive";
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;

    constructor(readonly stream: MediaStream) {}

    start() {
      this.state = "recording";
    }

    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["voice"], { type: "audio/webm" }) });
      this.onstop?.();
    }
  }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => petStateResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => textChatResponse })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "aud-speaking",
        status: "ready",
        voice_url: "/static/audio/speaking.wav",
        error: null,
        created_at: "now",
        updated_at: "now"
      })
    })
    .mockResolvedValueOnce({ ok: true, json: async () => voiceResponse })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "aud-voice",
        status: "ready",
        voice_url: "/static/audio/voice.wav",
        error: null,
        created_at: "now",
        updated_at: "now"
      })
    });
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: vi.fn() }]
      })
    }
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);

  render(<App />);
  await flush();

  const input = screen.getByPlaceholderText("输入一句话……");
  fireEvent.change(input, { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
  }

  expect(screen.getByRole("button", { name: "打断并说话" })).toBeInTheDocument();
  const clearCallsBeforeInterrupt = clearTimeoutSpy.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "打断并说话" }));
  expect(audioInstances[0].paused).toBe(true);
  expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThan(clearCallsBeforeInterrupt);
  await act(async () => {
    await Promise.resolve();
  });
  expect(screen.getByRole("button", { name: "点一下发送" })).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  fireEvent.click(screen.getByRole("button", { name: "点一下发送" }));
  await act(async () => {
    await Promise.resolve();
  });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/voice/chat",
    expect.objectContaining({ method: "POST" })
  );

  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
  }

  expect(audioInstances).toHaveLength(2);
  expect(audioInstances[0].paused).toBe(true);
  expect(audioInstances[0].loaded).toBe(true);

  audioInstances[0].onended?.();
  await act(async () => {
    await Promise.resolve();
  });
  expect(screen.queryByText("豆豆说完啦。")).not.toBeInTheDocument();
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: originalMediaDevices
  });
  vi.stubGlobal("MediaRecorder", originalMediaRecorder);
});

describe("more menu", () => {
  test("more toggle button exists and toggles touch area", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema_version: "0.1",
          name: "豆豆",
          mood: "idle",
          energy: 72,
          intimacy: 40,
          hunger: 30,
          cleanliness: 85,
          loneliness: 35,
          sleepiness: 15,
          mode: "idle"
        })
      })
      .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await flush();

    const moreBtn = screen.getByRole("button", { name: "更多互动" });
    expect(moreBtn).toBeInTheDocument();

    // Touch area should not be visible initially
    expect(screen.queryByRole("button", { name: "摸摸头" })).not.toBeInTheDocument();

    // Click more to show
    fireEvent.click(moreBtn);
    expect(screen.getByRole("button", { name: "摸摸头" })).toBeInTheDocument();
  });

  test("default interactions stay local and do not post pet event", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema_version: "0.1",
          name: "豆豆",
          mood: "idle",
          energy: 72,
          intimacy: 40,
          hunger: 30,
          cleanliness: 85,
          loneliness: 35,
          sleepiness: 15,
          mode: "idle"
        })
      })
      .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await flush();

    fireEvent.click(screen.getByRole("button", { name: "更多互动" }));
    fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));

    expect(screen.getByText("摸摸头…")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/pet/event")).toBe(false);
  });

  test("requires_model interaction still posts pet event", async () => {
    const petStateResponse = {
      schema_version: "0.1",
      name: "豆豆",
      mood: "idle",
      energy: 72,
      intimacy: 40,
      hunger: 30,
      cleanliness: 85,
      loneliness: 35,
      sleepiness: 15,
      mode: "idle"
    };
    const modelInteraction = [{
      ...interactionCatalogResponse[0],
      requires_model: true
    }];
    const modelResponse = {
      reply: "豆豆认真回应你。",
      mood: "happy",
      face_type: "happy",
      animation: "bounce",
      vibration: "none",
      voice_url: null,
      audio_job_id: null,
      pet_state: { ...petStateResponse, mood: "happy" as const },
      runtime: { event_id: "evt-model", skills_used: [] }
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "豆豆" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => petStateResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => modelInteraction })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => modelResponse });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await flush();

    fireEvent.click(screen.getByRole("button", { name: "更多互动" }));
    fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock.mock.calls.some(([url]) => url === "/api/pet/event")).toBe(true);
  });
});

test("audio retry failure keeps retry button visible with original job id", async () => {
  const petStateResponse = {
    schema_version: "0.1",
    name: "豆豆",
    mood: "idle",
    energy: 72,
    intimacy: 40,
    hunger: 30,
    cleanliness: 85,
    loneliness: 35,
    sleepiness: 15,
    mode: "idle"
  };
  const textChatResponse = {
    reply: "豆豆试着说。",
    mood: "happy",
    face_type: "happy",
    animation: "bounce",
    vibration: "none",
    voice_url: null,
    audio_job_id: "aud-failed",
    user_text: "你好",
    text_route: {
      selected: "fast_reply",
      thinking_mode: false,
      brain_provider: "test",
      timings_ms: {}
    },
    pet_state: { ...petStateResponse, mood: "happy" as const },
    runtime: { event_id: "evt-text", skills_used: [] }
  };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 1000, audio_progressive: {}, pet_name: "豆豆" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => petStateResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => textChatResponse })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "aud-failed",
        status: "failed",
        voice_url: null,
        error: "network",
        error_class: "network",
        created_at: "now",
        updated_at: "now"
      })
    })
    .mockRejectedValueOnce(new Error("retry network failure"));
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await flush();

  fireEvent.change(screen.getByPlaceholderText("输入一句话……"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(700);
  });

  expect(screen.getByRole("button", { name: "重试发声" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重试发声" }));
  await act(async () => {
    await Promise.resolve();
  });

  expect(screen.getByRole("button", { name: "重试发声" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/audio/jobs/aud-failed/retry", expect.any(Object));
});
