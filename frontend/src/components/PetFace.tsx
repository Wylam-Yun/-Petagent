import { expressionForKey } from "../pet/faces";
import type { AnimationName, ExpressionKey, Mood } from "../pet/types";

type PetFaceProps = {
  faceType: Mood;
  animation: AnimationName;
  expressionKey?: ExpressionKey | string | null;
};

export function PetFace({ faceType, animation, expressionKey }: PetFaceProps) {
  return (
    <div
      aria-label="豆豆表情"
      className={`pet-face animation-${animation}`}
      data-face-type={faceType}
      data-expression-key={expressionKey ?? ""}
    >
      {expressionForKey(expressionKey, faceType)}
    </div>
  );
}
