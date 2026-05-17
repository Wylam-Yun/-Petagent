import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { StatusBar } from "./StatusBar";
import type { PetState } from "../pet/types";

const state: PetState = {
  name: "Momo",
  mood: "happy",
  energy: 68,
  intimacy: 52,
  hunger: 30,
  cleanliness: 88,
  loneliness: 18,
  sleepiness: 42
};

describe("StatusBar", () => {
  test("keeps sleepiness internal instead of showing it as a duplicate main stat", () => {
    render(<StatusBar state={state} />);

    expect(screen.getByText("活力")).toBeInTheDocument();
    expect(screen.queryByText("困意")).not.toBeInTheDocument();
  });
});
