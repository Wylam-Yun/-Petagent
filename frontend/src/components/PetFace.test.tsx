import { render, screen } from "@testing-library/react";

import { PetFace } from "./PetFace";

test("PetFace renders the selected kaomoji and animation class", () => {
  render(<PetFace faceType="happy" animation="bounce" expressionKey="playful" />);

  expect(screen.getByLabelText("豆豆表情")).toHaveTextContent("(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧");
  expect(screen.getByLabelText("豆豆表情")).toHaveClass("animation-bounce");
  expect(screen.getByLabelText("豆豆表情")).toHaveAttribute("data-expression-key", "playful");
});
