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

const petCareIds: PetEventType[] = ["feed_momo", "pet_pat", "clean_face", "tuck_in"];
const companionIds: PetEventType[] = ["praise_momo", "comfort_me", "stay_with_me", "encourage_me", "take_a_break", "play_with_momo"];

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
  take_a_break: Pause,
  play_with_momo: Sparkles
};

type TouchAreaProps = {
  disabled: boolean;
  interactions: InteractionDefinition[];
  onPetEvent: (event: PetEventType) => void;
};

export function TouchArea({ disabled, interactions, onPetEvent }: TouchAreaProps) {
  const petCareActions = interactions.filter((item) => petCareIds.includes(item.event_id));
  const companionActions = interactions.filter((item) => companionIds.includes(item.event_id));
  const otherActions = interactions.filter(
    (item) => !petCareIds.includes(item.event_id) && !companionIds.includes(item.event_id)
  );

  return (
    <div className="touch-area">
      {petCareActions.length > 0 && (
        <div className="touch-group">
          <span className="touch-group-label">养宠</span>
          <div className="touch-group-buttons">
            {petCareActions.map((item) => {
              const Icon = iconMap[item.event_id] ?? Sparkles;
              return (
                <button
                  key={item.event_id}
                  aria-label={item.label}
                  className="touch-button"
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
      )}
      {companionActions.length > 0 && (
        <div className="touch-group">
          <span className="touch-group-label">陪伴</span>
          <div className="touch-group-buttons">
            {companionActions.map((item) => {
              const Icon = iconMap[item.event_id] ?? Sparkles;
              return (
                <button
                  key={item.event_id}
                  aria-label={item.label}
                  className="touch-button"
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
      )}
      {otherActions.length > 0 && (
        <div className="touch-group">
          <div className="touch-group-buttons">
            {otherActions.map((item) => {
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
      )}
    </div>
  );
}
