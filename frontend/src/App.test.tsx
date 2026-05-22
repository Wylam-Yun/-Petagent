import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import App from "./App";

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

test("App renders Momo and applies optimistic wiggle on pet_head", async () => {
  let resolveEvent: (value: unknown) => void = () => undefined;
  const eventPromise = new Promise((resolve) => {
    resolveEvent = resolve;
  });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "Momo" }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema_version: "0.1",
        name: "Momo",
        mood: "idle",
        energy: 72,
        intimacy: 40,
        hunger: 30,
        cleanliness: 85,
        loneliness: 35,
        sleepiness: 15,
        mode: "idle",
        last_interaction_at: "now",
        updated_at: "now"
      })
    })
    .mockResolvedValueOnce({ ok: true, json: async () => interactionCatalogResponse })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, received_at: "now" }) })
    .mockReturnValueOnce(eventPromise)
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
  await screen.findByText("Momo");

  fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));

  expect(screen.getByLabelText("Momo 表情")).toHaveClass("animation-wiggle");

  await act(async () => {
    resolveEvent({
      ok: true,
      json: async () => ({
        reply: "嘿嘿，Momo 在呢。",
        mood: "happy",
        face_type: "happy",
        animation: "bounce",
        vibration: "light",
        voice_url: null,
        audio_job_id: "aud-event",
        pet_state: {
          name: "Momo",
          mood: "happy",
          energy: 72,
          intimacy: 42,
          hunger: 30,
          cleanliness: 85,
          loneliness: 30,
          sleepiness: 15
        },
        runtime: { event_id: "evt-test", skills_used: [] }
      })
    });
  });

  await waitFor(() => expect(screen.getByText("Momo 说完啦。")).toBeInTheDocument());
});

describe("text chat", () => {
  test("typed text sends POST and applies response", async () => {
    const petStateResponse = {
      schema_version: "0.1",
      name: "Momo",
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
      reply: "好呀，Momo 帮你想。",
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
      .mockResolvedValueOnce({ ok: true, json: async () => ({ audio_wait_ms: 90000, audio_progressive: {}, pet_name: "Momo" }) })
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
    await screen.findByText("Momo");

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "帮我写两数之和" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(screen.getByText("Momo 说完啦。")).toBeInTheDocument());

    const [, textInit] = fetchMock.mock.calls[4];
    expect(textInit.method).toBe("POST");
    expect(JSON.parse(textInit.body as string)).toMatchObject({
      text: "帮我写两数之和",
      thinking_mode: false
    });
  });
});
