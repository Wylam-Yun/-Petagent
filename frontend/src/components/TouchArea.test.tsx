import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TouchArea } from "./TouchArea";

describe("TouchArea", () => {
  test("emits primary interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} onPetEvent={onPetEvent} />);

    fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));
    fireEvent.click(screen.getByRole("button", { name: "抱一下" }));
    fireEvent.click(screen.getByRole("button", { name: "陪我一下" }));

    expect(onPetEvent).toHaveBeenCalledWith("pet_head");
    expect(onPetEvent).toHaveBeenCalledWith("hug");
    expect(onPetEvent).toHaveBeenCalledWith("stay_with_me");
  });

  test("emits more interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} onPetEvent={onPetEvent} />);

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
    render(<TouchArea disabled={true} onPetEvent={() => undefined} />);

    expect(screen.getByRole("button", { name: "投喂" })).toBeDisabled();
  });
});
