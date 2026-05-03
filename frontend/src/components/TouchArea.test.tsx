import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { TouchArea } from "./TouchArea";

test("TouchArea emits pet_head when the head button is clicked", () => {
  const onPetEvent = vi.fn();
  render(<TouchArea disabled={false} onPetEvent={onPetEvent} />);

  fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));

  expect(onPetEvent).toHaveBeenCalledWith("pet_head");
});

test("TouchArea disables controls while busy", () => {
  render(<TouchArea disabled={true} onPetEvent={() => undefined} />);

  expect(screen.getByRole("button", { name: "戳戳脸" })).toBeDisabled();
});
