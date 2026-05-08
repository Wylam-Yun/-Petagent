import {
  HandHeart,
  HeartHandshake,
  Sparkles,
  Hand,
  Star,
  Cookie,
  Heart,
  ThumbsUp,
  MessageCircle,
  Moon,
  SprayCan,
  Coffee,
  Pause
} from "lucide-react";

import type { PetEventType } from "../pet/types";

type ActionDef = { event: PetEventType; label: string; icon: React.ElementType };

const primaryActions: ActionDef[] = [
  { event: "pet_head", label: "摸摸头", icon: HandHeart },
  { event: "hug", label: "抱一下", icon: HeartHandshake },
  { event: "stay_with_me", label: "陪我一下", icon: Sparkles }
];

const moreActions: ActionDef[] = [
  { event: "pet_pat", label: "拍拍", icon: Hand },
  { event: "praise_momo", label: "夸夸", icon: Star },
  { event: "feed_momo", label: "投喂", icon: Cookie },
  { event: "comfort_me", label: "安慰我", icon: Heart },
  { event: "encourage_me", label: "鼓励我", icon: ThumbsUp },
  { event: "listen_to_me", label: "听我吐槽", icon: MessageCircle },
  { event: "tuck_in", label: "哄睡", icon: Moon },
  { event: "clean_face", label: "擦擦脸", icon: SprayCan },
  { event: "quiet_company", label: "安静待着", icon: Coffee },
  { event: "take_a_break", label: "休息会儿", icon: Pause }
];

type TouchAreaProps = {
  disabled: boolean;
  onPetEvent: (event: PetEventType) => void;
};

export function TouchArea({ disabled, onPetEvent }: TouchAreaProps) {
  return (
    <div className="touch-area">
      <div className="touch-primary">
        {primaryActions.map(({ event, label, icon: Icon }) => (
          <button
            key={event}
            aria-label={label}
            className="touch-button primary"
            disabled={disabled}
            type="button"
            onClick={() => onPetEvent(event)}
          >
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
      <div className="touch-more">
        {moreActions.map(({ event, label, icon: Icon }) => (
          <button
            key={event}
            aria-label={label}
            className="touch-button compact"
            disabled={disabled}
            type="button"
            onClick={() => onPetEvent(event)}
          >
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
