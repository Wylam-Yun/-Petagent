import { Battery, Heart, Sparkles } from "lucide-react";

import type { PetState } from "../pet/types";

type StatusBarProps = {
  state: PetState;
};

export function StatusBar({ state }: StatusBarProps) {
  return (
    <section className="status-bar" aria-label="豆豆状态">
      <StatusItem icon={<Heart />} label="亲密" value={state.intimacy} />
      <StatusItem icon={<Battery />} label="活力" value={state.energy} />
      <StatusItem icon={<Sparkles />} label="心情" value={state.mood} />
    </section>
  );
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
