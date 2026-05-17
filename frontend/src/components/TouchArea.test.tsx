import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TouchArea } from "./TouchArea";

const interactions = [
  { event_id: "pet_head", label: "摸摸头", group: "pet_care", default_mood: "shy", default_animation: "wiggle", state_semantics: {} },
  { event_id: "hug", label: "抱一下", group: "pet_care", default_mood: "happy", default_animation: "bounce", state_semantics: {} },
  { event_id: "stay_with_me", label: "陪我一下", group: "emotional_companion", default_mood: "happy", default_animation: "breathing", state_semantics: {} },
  { event_id: "pet_pat", label: "拍拍", group: "pet_care", default_mood: "happy", default_animation: "wiggle", state_semantics: {} },
  { event_id: "praise_momo", label: "夸夸", group: "pet_care", default_mood: "happy", default_animation: "jump", state_semantics: {} },
  { event_id: "feed_momo", label: "投喂", group: "pet_care", default_mood: "happy", default_animation: "bounce", state_semantics: {} },
  { event_id: "comfort_me", label: "安慰我", group: "emotional_companion", default_mood: "concerned", default_animation: "tilt", state_semantics: {} },
  { event_id: "encourage_me", label: "鼓励我", group: "emotional_companion", default_mood: "excited", default_animation: "jump", state_semantics: {} },
  { event_id: "listen_to_me", label: "听我吐槽", group: "emotional_companion", default_mood: "thinking", default_animation: "tilt", state_semantics: {} },
  { event_id: "tuck_in", label: "哄睡", group: "pet_care", default_mood: "sleepy", default_animation: "slowBlink", state_semantics: {} },
  { event_id: "clean_face", label: "擦擦脸", group: "pet_care", default_mood: "happy", default_animation: "wiggle", state_semantics: {} },
  { event_id: "quiet_company", label: "安静待着", group: "emotional_companion", default_mood: "idle", default_animation: "breathing", state_semantics: {} },
  { event_id: "take_a_break", label: "休息会儿", group: "emotional_companion", default_mood: "sleepy", default_animation: "slowBlink", state_semantics: {} }
];

describe("TouchArea", () => {
  test("renders interaction labels from runtime catalog", () => {
    const onPetEvent = vi.fn();
    render(
      <TouchArea
        disabled={false}
        interactions={[
          {
            event_id: "feed_momo",
            label: "喂 Momo 一口",
            group: "pet_care",
            default_mood: "happy",
            default_animation: "bounce",
            state_semantics: {}
          }
        ]}
        onPetEvent={onPetEvent}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "喂 Momo 一口" }));

    expect(onPetEvent).toHaveBeenCalledWith("feed_momo");
    expect(screen.queryByRole("button", { name: "投喂" })).not.toBeInTheDocument();
  });

  test("emits primary interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} interactions={interactions} onPetEvent={onPetEvent} />);

    fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));
    fireEvent.click(screen.getByRole("button", { name: "抱一下" }));
    fireEvent.click(screen.getByRole("button", { name: "陪我一下" }));

    expect(onPetEvent).toHaveBeenCalledWith("pet_head");
    expect(onPetEvent).toHaveBeenCalledWith("hug");
    expect(onPetEvent).toHaveBeenCalledWith("stay_with_me");
  });

  test("emits more interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} interactions={interactions} onPetEvent={onPetEvent} />);

    for (const name of ["拍拍", "夸夸", "投喂", "安慰我", "鼓励我", "听我吐槽", "哄睡", "擦擦脸", "安静待着", "休息会儿"]) {
      fireEvent.click(screen.getByRole("button", { name }));
    }

    expect(onPetEvent).toHaveBeenCalledWith("pet_pat");
    expect(onPetEvent).toHaveBeenCalledWith("praise_momo");
    expect(onPetEvent).toHaveBeenCalledWith("feed_momo");
    expect(onPetEvent).toHaveBeenCalledWith("comfort_me");
    expect(onPetEvent).toHaveBeenCalledWith("encourage_me");
    expect(onPetEvent).toHaveBeenCalledWith("listen_to_me");
    expect(onPetEvent).toHaveBeenCalledWith("tuck_in");
    expect(onPetEvent).toHaveBeenCalledWith("clean_face");
    expect(onPetEvent).toHaveBeenCalledWith("quiet_company");
    expect(onPetEvent).toHaveBeenCalledWith("take_a_break");
  });

  test("disables controls while busy", () => {
    render(<TouchArea disabled={true} interactions={interactions} onPetEvent={() => undefined} />);

    expect(screen.getByRole("button", { name: "投喂" })).toBeDisabled();
  });
});
