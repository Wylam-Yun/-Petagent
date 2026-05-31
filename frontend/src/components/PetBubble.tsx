type PetBubbleProps = {
  text: string;
  busy?: boolean;
};

export function PetBubble({ text, busy = false }: PetBubbleProps) {
  return (
    <div className="pet-bubble" aria-live="polite">
      {busy ? "唔，我想一下…" : text}
    </div>
  );
}
