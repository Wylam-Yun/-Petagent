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

import type { InteractionDefinition, PetEventType } from "../pet/types";

const primaryEventIds: PetEventType[] = ["pet_head", "hug", "stay_with_me"];

const iconMap: Partial<Record<PetEventType, React.ElementType>> = {
  pet_head: HandHeart,
  hug: HeartHandshake,
  stay_with_me: Sparkles,
  pet_pat: Hand,
  praise_momo: Star,
  feed_momo: Cookie,
  comfort_me: Heart,
  encourage_me: ThumbsUp,
  listen_to_me: MessageCircle,
  tuck_in: Moon,
  clean_face: SprayCan,
  quiet_company: Coffee,
  take_a_break: Pause
};

type TouchAreaProps = {
  disabled: boolean;
  interactions: InteractionDefinition[];
  onPetEvent: (event: PetEventType) => void;
};

export function TouchArea({ disabled, interactions, onPetEvent }: TouchAreaProps) {
  const primaryActions = interactions.filter((item) => primaryEventIds.includes(item.event_id));
  const moreActions = interactions.filter((item) => !primaryEventIds.includes(item.event_id));

  return (
    <div className="touch-area">
      <div className="touch-primary">
        {primaryActions.map((item) => {
          const Icon = iconMap[item.event_id] ?? Sparkles;
          return (
          <button
            key={item.event_id}
            aria-label={item.label}
            className="touch-button primary"
            disabled={disabled}
            type="button"
            onClick={() => onPetEvent(item.event_id)}
          >
            <Icon aria-hidden="true" />
            <span>{item.label}</span>
          </button>
          );
        })}
      </div>
      <div className="touch-more">
        {moreActions.map((item) => {
          const Icon = iconMap[item.event_id] ?? Sparkles;
          return (
          <button
            key={item.event_id}
            aria-label={item.label}
            className="touch-button compact"
            disabled={disabled}
            type="button"
            onClick={() => onPetEvent(item.event_id)}
          >
            <Icon aria-hidden="true" />
            <span>{item.label}</span>
          </button>
          );
        })}
      </div>
    </div>
  );
}
