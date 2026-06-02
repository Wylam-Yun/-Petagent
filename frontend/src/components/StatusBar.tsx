import { Battery, Heart, Sparkles } from "lucide-react";

import type { Mood, PetState } from "../pet/types";

type StatusBarProps = {
  state: PetState;
};

export function StatusBar({ state }: StatusBarProps) {
  return (
    <section className="status-bar" aria-label="豆豆状态">
      <StatusItem icon={<Heart />} label="亲密" value={state.intimacy} />
      <StatusItem icon={<Battery />} label="活力" value={state.energy} />
      <StatusItem icon={<Sparkles />} label="心情" value={moodLabel(state.mood)} />
    </section>
  );
}

const moodLabels: Record<Mood, string> = {
  idle: "安静",
  happy: "开心",
  sad: "低落",
  sleepy: "犯困",
  tired: "累了",
  angry: "生气",
  shy: "害羞",
  thinking: "思考",
  concerned: "担心",
  excited: "兴奋",
  lonely: "想陪"
};

function moodLabel(mood: Mood): string {
  return moodLabels[mood] ?? "安静";
}

function StatusItem({
  icon,
  label,
  value
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="status-item">
      <span className="status-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="status-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
