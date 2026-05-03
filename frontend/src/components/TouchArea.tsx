import { HandHeart, HeartHandshake, SmilePlus } from "lucide-react";

import type { PetEventType } from "../pet/types";

type TouchAreaProps = {
  disabled: boolean;
  onPetEvent: (event: PetEventType) => void;
};

export function TouchArea({ disabled, onPetEvent }: TouchAreaProps) {
  return (
    <div className="touch-area">
      <button
        aria-label="摸摸头"
        className="touch-button primary"
        disabled={disabled}
        type="button"
        onClick={() => onPetEvent("pet_head")}
      >
        <HandHeart aria-hidden="true" />
        <span>摸摸头</span>
      </button>
      <button
        aria-label="戳戳脸"
        className="touch-button"
        disabled={disabled}
        type="button"
        onClick={() => onPetEvent("poke_face")}
      >
        <SmilePlus aria-hidden="true" />
        <span>戳戳脸</span>
      </button>
      <button
        aria-label="抱一下"
        className="touch-button"
        disabled={disabled}
        type="button"
        onClick={() => onPetEvent("hug")}
      >
        <HeartHandshake aria-hidden="true" />
        <span>抱一下</span>
      </button>
    </div>
  );
}
