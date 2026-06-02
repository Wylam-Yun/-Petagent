import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { StatusBar } from "./StatusBar";
import type { PetState } from "../pet/types";

const state: PetState = {
  name: "豆豆",
  mood: "happy",
  energy: 68,
  intimacy: 52,
  hunger: 30,
  cleanliness: 88,
  loneliness: 18,
  sleepiness: 42
};

describe("StatusBar", () => {
  test("shows only intimacy, energy, mood — no internal stats", () => {
    render(<StatusBar state={state} />);

    expect(screen.getByLabelText("豆豆状态")).toBeInTheDocument();
    expect(screen.getByText("亲密")).toBeInTheDocument();
    expect(screen.getByText("活力")).toBeInTheDocument();
    expect(screen.getByText("心情")).toBeInTheDocument();
    expect(screen.getByText("开心")).toBeInTheDocument();
    expect(screen.queryByText("happy")).not.toBeInTheDocument();
    expect(screen.queryByText("想陪")).not.toBeInTheDocument();
    expect(screen.queryByText("困意")).not.toBeInTheDocument();
  });
});
