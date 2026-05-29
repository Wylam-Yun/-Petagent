import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { DoudouSprite } from "./DoudouSprite";

const OriginalImage = globalThis.Image;

function mockImageEvent(eventType: "load" | "error") {
  // @ts-expect-error replacing global Image constructor
  globalThis.Image = class extends OriginalImage {
    constructor() {
      super();
      setTimeout(() => {
        this.dispatchEvent(new Event(eventType));
      }, 0);
    }
  };
}

describe("DoudouSprite", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.Image = OriginalImage;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  async function renderAndWaitForLoad(ui: React.ReactElement) {
    const result = render(ui);
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    return result;
  }

  it("renders with correct dimensions after asset loads", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" });
    expect((sprite as HTMLElement).style.width).toBe("192px");
    expect((sprite as HTMLElement).style.height).toBe("208px");
    expect((sprite as HTMLElement).dataset.action).toBe("idle");
  });

  it("renders with spritesheet background image", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" });
    const bg = (sprite as HTMLElement).style.backgroundImage;
    expect(bg).toContain("spritesheet");
    expect(bg).toContain(".webp");
  });

  it("sets correct background size for atlas", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" });
    expect((sprite as HTMLElement).style.backgroundSize).toBe("1536px 1872px");
  });

  it("starts at frame 0 position", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" });
    expect((sprite as HTMLElement).style.backgroundPosition).toBe("0px 0px");
  });

  it("advances frame after interval", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" });

    act(() => {
      vi.advanceTimersByTime(180);
    });

    expect((sprite as HTMLElement).style.backgroundPosition).toBe("-192px 0px");
  });

  it("uses pixelated rendering", async () => {
    mockImageEvent("load");
    await renderAndWaitForLoad(<DoudouSprite action="idle" />);
    const sprite = screen.getByRole("img", { name: "豆豆" }) as HTMLElement;
    expect(sprite.style.imageRendering).toBe("pixelated");
  });

  it("calls onTap when clicked", async () => {
    mockImageEvent("load");
    const onTap = vi.fn();
    await renderAndWaitForLoad(<DoudouSprite action="idle" onTap={onTap} />);
    const sprite = screen.getByRole("img", { name: "豆豆" });
    fireEvent.click(sprite);
    expect(onTap).toHaveBeenCalledTimes(1);
  });

  it("calls onOneShotComplete when one-shot finishes", async () => {
    mockImageEvent("load");
    const onComplete = vi.fn();
    await renderAndWaitForLoad(
      <DoudouSprite action="waving" onOneShotComplete={onComplete} />,
    );

    // waving has 4 frames, advance past all of them
    act(() => {
      vi.advanceTimersByTime(180 * 4);
    });

    expect(onComplete).toHaveBeenCalledWith("waving");
  });

  it("does not call onOneShotComplete for loop animations", async () => {
    mockImageEvent("load");
    const onComplete = vi.fn();
    await renderAndWaitForLoad(
      <DoudouSprite action="idle" onOneShotComplete={onComplete} />,
    );

    act(() => {
      vi.advanceTimersByTime(180 * 20);
    });

    expect(onComplete).not.toHaveBeenCalled();
  });

  it("resets frame when action changes", async () => {
    mockImageEvent("load");
    const { rerender } = await renderAndWaitForLoad(
      <DoudouSprite action="idle" />,
    );
    const sprite = screen.getByRole("img", { name: "豆豆" });

    act(() => {
      vi.advanceTimersByTime(180 * 3);
    });

    rerender(<DoudouSprite action="waving" />);

    // Should be at frame 0 of waving (row 3)
    expect((sprite as HTMLElement).style.backgroundPosition).toBe("0px -624px");
    expect((sprite as HTMLElement).dataset.action).toBe("waving");
  });

  it("shows fallback when asset fails to load", async () => {
    mockImageEvent("error");
    const { container } = await renderAndWaitForLoad(
      <DoudouSprite action="idle" />,
    );
    const fallback = container.querySelector(".doudou-sprite--fallback");
    expect(fallback).toBeTruthy();
    expect(fallback!.textContent).toBe("(=^-^=)");
  });

  it("fallback has correct dimensions", async () => {
    mockImageEvent("error");
    const { container } = await renderAndWaitForLoad(
      <DoudouSprite action="idle" />,
    );
    const fallback = container.querySelector(
      ".doudou-sprite--fallback",
    ) as HTMLElement;
    expect(fallback.style.width).toBe("192px");
    expect(fallback.style.height).toBe("208px");
  });

  it("fallback is clickable", async () => {
    mockImageEvent("error");
    const onTap = vi.fn();
    const { container } = await renderAndWaitForLoad(
      <DoudouSprite action="idle" onTap={onTap} />,
    );
    const fallback = container.querySelector(".doudou-sprite--fallback")!;
    fireEvent.click(fallback);
    expect(onTap).toHaveBeenCalledTimes(1);
  });
});
