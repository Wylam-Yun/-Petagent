import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TextInputBar } from "./TextInputBar";

describe("TextInputBar", () => {
  test("does not submit empty text", () => {
    const onSubmit = vi.fn();
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("submits trimmed text and clears input on success", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "  我今天有点累  " } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).toHaveBeenCalledWith("我今天有点累");
  });

  test("enter submits text", () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "夸夸豆豆" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSubmit).toHaveBeenCalledWith("夸夸豆豆");
  });

  test("keeps text when submission fails without leaking rejection", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("network"));
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "别丢掉这句话" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByDisplayValue("别丢掉这句话")).toBeInTheDocument();
  });
});
