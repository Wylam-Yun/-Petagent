import { faceForType } from "../pet/faces";
import type { AnimationName, Mood } from "../pet/types";

type PetFaceProps = {
  faceType: Mood;
  animation: AnimationName;
};

export function PetFace({ faceType, animation }: PetFaceProps) {
  return (
    <div
      aria-label="Momo 表情"
      className={`pet-face animation-${animation}`}
      data-face-type={faceType}
    >
      {faceForType(faceType)}
    </div>
  );
}
