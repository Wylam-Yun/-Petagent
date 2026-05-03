import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

test("App renders Momo and applies optimistic wiggle on pet_head", async () => {
  let resolveEvent: (value: unknown) => void = () => undefined;
  const eventPromise = new Promise((resolve) => {
    resolveEvent = resolve;
  });
  const fetchMock = vi.fn()
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
    .mockReturnValueOnce(eventPromise);
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

  await waitFor(() => expect(screen.getByText("嘿嘿，Momo 在呢。")).toBeInTheDocument());
});
