import { render, screen } from "@testing-library/react";

import { PetFace } from "./PetFace";

test("PetFace renders the selected kaomoji and animation class", () => {
  render(<PetFace faceType="happy" animation="bounce" />);

  expect(screen.getByLabelText("豆豆表情")).toHaveTextContent("(^▽^)");
  expect(screen.getByLabelText("豆豆表情")).toHaveClass("animation-bounce");
});
