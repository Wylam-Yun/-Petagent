import { useEffect, useRef, useState, useCallback } from "react";
import {
  doudouManifest,
  getFramePosition,
  type DoudouAction,
  type DoudouSpriteManifest,
} from "../pet/doudouSprites";

type DoudouSpriteProps = {
  action: DoudouAction;
  /** Called when a one-shot animation finishes its last frame. */
  onOneShotComplete?: (action: DoudouAction) => void;
  /** Tap handler for sprite interaction. */
  onTap?: () => void;
};

export function DoudouSprite({
  action,
  onOneShotComplete,
  onTap,
}: DoudouSpriteProps) {
  const [frameIndex, setFrameIndex] = useState(0);
  const [assetState, setAssetState] = useState<"loading" | "loaded" | "error">(
    "loading",
  );
  const frameRef = useRef(0);
  const actionRef = useRef(action);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completeRef = useRef(onOneShotComplete);
  completeRef.current = onOneShotComplete;

  const manifest: DoudouSpriteManifest = doudouManifest;
  const def = manifest.animations[action];

  // Preload spritesheet via Image() to detect load/error
  useEffect(() => {
    const img = new Image();
    img.onload = () => setAssetState("loaded");
    img.onerror = () => setAssetState("error");
    img.src = manifest.imageUrl;
  }, [manifest.imageUrl]);

  // Reset frame when action changes
  useEffect(() => {
    if (actionRef.current !== action) {
      actionRef.current = action;
      frameRef.current = 0;
      setFrameIndex(0);
    }
  }, [action]);

  // Frame animation loop
  useEffect(() => {
    if (assetState !== "loaded") return;

    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    timerRef.current = setInterval(() => {
      const currentDef = manifest.animations[actionRef.current];
      const nextFrame = frameRef.current + 1;

      if (nextFrame >= currentDef.frames) {
        if (currentDef.type === "one-shot") {
          if (timerRef.current) clearInterval(timerRef.current);
          completeRef.current?.(actionRef.current);
          return;
        }
        frameRef.current = 0;
        setFrameIndex(0);
      } else {
        frameRef.current = nextFrame;
        setFrameIndex(nextFrame);
      }
    }, def.frameMs);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [action, def.frameMs, assetState, manifest]);

  const pos = getFramePosition(manifest, action, frameIndex);
  const bgSize = `${manifest.atlasWidth}px ${manifest.atlasHeight}px`;

  const handleClick = useCallback(() => {
    onTap?.();
  }, [onTap]);

  if (assetState === "error") {
    return (
      <div
        className="doudou-sprite doudou-sprite--fallback"
        style={{
          width: manifest.cellWidth,
          height: manifest.cellHeight,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 48,
        }}
        aria-label="豆豆"
        data-action={action}
        onClick={handleClick}
      >
        (=^-^=)
      </div>
    );
  }

  return (
    <div
      className="doudou-sprite"
      role="img"
      aria-label="豆豆"
      data-action={action}
      style={{
        width: manifest.cellWidth,
        height: manifest.cellHeight,
        backgroundImage: `url(${manifest.imageUrl})`,
        backgroundSize: bgSize,
        backgroundPosition: `${pos.x}px ${pos.y}px`,
        backgroundRepeat: "no-repeat",
        imageRendering: "pixelated",
        cursor: onTap ? "pointer" : undefined,
      }}
      onClick={handleClick}
    />
  );
}
