import type { MouseEventHandler } from "react";
import type { PetTone } from "../pet/types";

interface SpeechBubbleProps {
  message: string;
  tone: PetTone;
  onClick?: MouseEventHandler<HTMLElement>;
  onDoubleClick?: MouseEventHandler<HTMLElement>;
  onContextMenu?: MouseEventHandler<HTMLElement>;
  onOpenDialogue?: MouseEventHandler<HTMLButtonElement>;
}

export function SpeechBubble({
  message,
  tone,
  onClick,
  onDoubleClick,
  onContextMenu,
  onOpenDialogue,
}: SpeechBubbleProps) {
  return (
    <section
      className="speech-bubble"
      data-tone={tone}
      aria-live="polite"
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onContextMenu={onContextMenu}
    >
      <div className="speech-bubble-row">
        <button
          className="bubble-open-button"
          type="button"
          onClick={onOpenDialogue}
          aria-label="Open dialogue window"
          title="Open dialogue"
        >
          <span className="expand-entry-icon" aria-hidden="true" />
        </button>
        <span>{message}</span>
      </div>
    </section>
  );
}
