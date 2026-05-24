import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";

import App from "./App";

const OriginalImage = globalThis.Image;

function mockImageLoad() {
  // @ts-expect-error replacing global Image constructor
  globalThis.Image = class extends OriginalImage {
    constructor() {
      super();
      setTimeout(() => {
        this.dispatchEvent(new Event("load"));
      }, 0);
    }
  };
}

class MockAudio {
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly src: string) {}

  play() {
    window.setTimeout(() => this.onended?.(), 0);
    return Promise.resolve();
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
    state_semantics: {}
  }
];

beforeEach(() => {
  vi.useFakeTimers();
  mockImageLoad();
});

afterEach(() => {
  globalThis.Image = OriginalImage;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function flush() {
  // Advance enough for Image onload, fetch responses, and initial renders.
  // Do NOT use runAllTimersAsync — the ambient setInterval would loop forever.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
}

test("App renders 豆豆 and shows sprite", async () => {
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
  // DoudouSprite should render (with aria-label "豆豆")
  const sprites = screen.getAllByLabelText("豆豆");
  expect(sprites.length).toBeGreaterThanOrEqual(1);
});

test("tap on sprite shows local reaction before backend responds", async () => {
  let resolveEvent: (value: unknown) => void = () => undefined;
  const eventPromise = new Promise((resolve) => {
    resolveEvent = resolve;
  });
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
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
    .mockReturnValueOnce(eventPromise) // tap backend sync (pet_head)
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: "aud-event",
        status: "ready",
        voice_url: "/static/audio/test.wav",
        error: null,
        created_at: "now",
        updated_at: "now"
      })
    });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await flush();

  // Find the sprite (role="img" with aria-label "豆豆")
  const sprite = screen.getAllByLabelText("豆豆").find(
    (el) => el.getAttribute("role") === "img"
  );
  expect(sprite).toBeTruthy();

  // Tap the sprite
  fireEvent.click(sprite!);

  // Bubble should show a local tap reaction immediately (no waiting for backend)
  const bubbleTexts = ["摸到了。", "嗯~", "喵~", "在的在的。"];
  const bubble = document.querySelector(".pet-bubble")!;
  expect(bubbleTexts.some((t) => bubble.textContent?.includes(t))).toBe(true);
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
        selected: "slow",
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
});
