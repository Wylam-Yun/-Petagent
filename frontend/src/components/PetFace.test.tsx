import { render, screen } from "@testing-library/react";

import { PetFace } from "./PetFace";

test("PetFace renders the selected kaomoji and animation class", () => {
  render(<PetFace faceType="happy" animation="bounce" />);

  expect(screen.getByLabelText("Momo 表情")).toHaveTextContent("(^▽^)");
  expect(screen.getByLabelText("Momo 表情")).toHaveClass("animation-bounce");
});
