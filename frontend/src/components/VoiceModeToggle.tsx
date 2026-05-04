import { Brain, Zap } from "lucide-react";

type VoiceModeToggleProps = {
  thinkingMode: boolean;
  onChange: (thinkingMode: boolean) => void;
};

export function VoiceModeToggle({ thinkingMode, onChange }: VoiceModeToggleProps) {
  return (
    <label className={`voice-mode-toggle ${thinkingMode ? "is-thinking" : ""}`}>
      <span className="voice-mode-label">
        {thinkingMode ? <Brain aria-hidden="true" /> : <Zap aria-hidden="true" />}
        <span>思考模式</span>
      </span>
      <input
        aria-label="思考模式"
        checked={thinkingMode}
        role="switch"
        type="checkbox"
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
      <span className="voice-mode-track" aria-hidden="true">
        <span className="voice-mode-thumb" />
      </span>
    </label>
  );
}
