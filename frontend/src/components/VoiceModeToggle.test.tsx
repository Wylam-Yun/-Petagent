import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { VoiceModeToggle } from "./VoiceModeToggle";

describe("VoiceModeToggle", () => {
  test("defaults to fast mode and toggles thinking mode", () => {
    const onChange = vi.fn();
    render(<VoiceModeToggle thinkingMode={false} onChange={onChange} />);

    expect(screen.getByRole("switch", { name: "思考模式" })).not.toBeChecked();

    fireEvent.click(screen.getByRole("switch", { name: "思考模式" }));

    expect(onChange).toHaveBeenCalledWith(true);
  });
});
