import type { MouseEvent } from "react";
import { SpeechBubble } from "./SpeechBubble";
import type { usePetController } from "../pet/usePetController";

type PetController = ReturnType<typeof usePetController>;

interface PetViewProps {
  controller: PetController;
  onStartDrag: () => void;
  onMinimize: () => void;
  onClose: () => void;
  onOpenDialogue: () => void;
}

export function PetView({
  controller,
  onStartDrag,
  onMinimize,
  onClose,
  onOpenDialogue,
}: PetViewProps) {
  const { state, view } = controller;

  function handleMouseEnter() {
    if (state !== "sleep") {
      controller.follow("hover");
    }
  }

  function handleMouseLeave() {
    if (state === "follow") {
      controller.idle("leave");
    }
  }

  function handleClick(event: MouseEvent<HTMLDivElement>) {
    event.stopPropagation();

    if (event.detail !== 1 || state === "sleep") {
      return;
    }

    controller.talk("click");
  }

  function handleDoubleClick(event: MouseEvent<HTMLDivElement>) {
    event.stopPropagation();
    controller.toggleSleep("double-click");
  }

  function handleContextMenu(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    controller.toggleSleep("context-menu");
  }

  function handleOpenDialogue(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (state !== "sleep") {
      controller.talk("click");
    }
    onOpenDialogue();
  }

  return (
    <main className="pet-shell" data-pet-state={state}>
      <div className="window-actions">
        <button
          className="window-action"
          type="button"
          onClick={onMinimize}
          aria-label="Minimize"
          title="Minimize"
        >
          -
        </button>
        <button
          className="window-action close"
          type="button"
          onClick={onClose}
          aria-label="Close"
          title="Close"
        >
          x
        </button>
      </div>

      <div
        className="pet-stage"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <SpeechBubble
          message={view.message}
          tone={view.tone}
          onClick={handleClick}
          onDoubleClick={handleDoubleClick}
          onContextMenu={handleContextMenu}
          onOpenDialogue={handleOpenDialogue}
        />

        <div
          className="pet-drag-region"
          data-tauri-drag-region
          onMouseDown={onStartDrag}
        >
          <img
            className="pet-image"
            src={view.image}
            alt={view.imageAlt}
            draggable={false}
            data-tauri-drag-region
          />
        </div>
      </div>
    </main>
  );
}
