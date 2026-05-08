import { SendHorizontal } from "lucide-react";
import { useState } from "react";

type TextInputBarProps = {
  disabled: boolean;
  onSubmit: (text: string) => Promise<boolean | void> | boolean | void;
};

export function TextInputBar({ disabled, onSubmit }: TextInputBarProps) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const isDisabled = disabled || submitting;

  async function submit() {
    const text = value.trim();
    if (!text || isDisabled) return;
    setSubmitting(true);
    setError("");
    try {
      const ok = await onSubmit(text);
      if (ok !== false) {
        setValue("");
      }
    } catch {
      setError("发送没成功，文字还留着。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="text-input-bar"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <input
        aria-label="文字输入"
        disabled={isDisabled}
        placeholder="输入一句话……"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void submit();
          }
        }}
      />
      <button aria-label="发送" disabled={isDisabled || !value.trim()} type="submit">
        <SendHorizontal aria-hidden="true" />
        <span>发送</span>
      </button>
      {error ? <span className="text-input-error">{error}</span> : null}
    </form>
  );
}
