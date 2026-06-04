import { render, screen } from "@testing-library/react";

import { PetFace } from "./PetFace";

test("PetFace renders the selected static kaomoji", () => {
  render(<PetFace faceType="happy" animation="bounce" expressionKey="playful" />);

  expect(screen.getByLabelText("豆豆表情")).toHaveTextContent("(^_~)");
  expect(screen.getByLabelText("豆豆表情")).not.toHaveClass("animation-bounce");
  expect(screen.getByLabelText("豆豆表情")).toHaveAttribute("data-animation", "bounce");
  expect(screen.getByLabelText("豆豆表情")).toHaveAttribute("data-expression-key", "playful");
});
