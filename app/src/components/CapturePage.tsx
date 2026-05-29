import { invoke } from "@tauri-apps/api/core";
import { emitTo } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { PointerEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import type { CaptureErrorEvent, CaptureImageEvent, ImagePayload } from "../llm/types";

type SelectionRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type DragPoint = {
  x: number;
  y: number;
};

type CaptureScreenRegionRequest = {
  x: number;
  y: number;
  width: number;
  height: number;
};

function normalizeRect(start: DragPoint, end: DragPoint): SelectionRect {
  const left = Math.min(start.x, end.x);
  const top = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);

  return { left, top, width, height };
}

function readPrompt() {
  const prompt = new URLSearchParams(window.location.search).get("prompt");
  return prompt?.trim() || "请解释这张截图中的内容。";
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      window.setTimeout(() => reject(new Error("Capture timed out.")), ms);
    }),
  ]);
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max));
}

export function CapturePage() {
  const [startPoint, setStartPoint] = useState<DragPoint | null>(null);
  const [currentPoint, setCurrentPoint] = useState<DragPoint | null>(null);
  const [selectedRect, setSelectedRect] = useState<SelectionRect | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const prompt = useMemo(readPrompt, []);
  const dragRect = startPoint && currentPoint ? normalizeRect(startPoint, currentPoint) : null;
  const activeRect = dragRect ?? selectedRect;
  const toolbarStyle = selectedRect
    ? {
        left: clamp(selectedRect.left + selectedRect.width - 132, 12, window.innerWidth - 150),
        top: selectedRect.top > 52 ? selectedRect.top - 44 : selectedRect.top + selectedRect.height + 12,
      }
    : undefined;

  useEffect(() => {
    async function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        await closeCaptureWindow();
      }

      if ((event.key === "Enter" || event.key === " ") && selectedRect && !isCapturing) {
        event.preventDefault();
        await captureSelection(selectedRect);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isCapturing, selectedRect]);

  function handlePointerDown(event: PointerEvent<HTMLElement>) {
    if (isCapturing) {
      return;
    }

    const point = { x: event.clientX, y: event.clientY };
    setStartPoint(point);
    setCurrentPoint(point);
    setSelectedRect(null);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent<HTMLElement>) {
    if (!startPoint || isCapturing) {
      return;
    }

    setCurrentPoint({ x: event.clientX, y: event.clientY });
  }

  function handlePointerUp(event: PointerEvent<HTMLElement>) {
    if (!startPoint || !currentPoint || isCapturing) {
      return;
    }

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    const selectedRect = normalizeRect(startPoint, { x: event.clientX, y: event.clientY });
    setStartPoint(null);
    setCurrentPoint(null);

    if (selectedRect.width < 8 || selectedRect.height < 8) {
      setSelectedRect(null);
      return;
    }

    setSelectedRect(selectedRect);
  }

  function handlePointerCancel(event: PointerEvent<HTMLElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    setStartPoint(null);
    setCurrentPoint(null);
  }

  async function captureSelection(selection: SelectionRect) {
    setIsCapturing(true);

    try {
      const currentWindow = getCurrentWindow();
      const position = await currentWindow.outerPosition();
      const scaleFactor = await currentWindow.scaleFactor();
      const request: CaptureScreenRegionRequest = {
        x: Math.round(position.x + selection.left * scaleFactor),
        y: Math.round(position.y + selection.top * scaleFactor),
        width: Math.round(selection.width * scaleFactor),
        height: Math.round(selection.height * scaleFactor),
      };

      await currentWindow.hide();
      await wait(160);

      const image = await withTimeout(
        invoke<ImagePayload>("capture_screen_region", { request }),
        8000,
      );
      const payload: CaptureImageEvent = {
        image,
        prompt,
        source: "selection",
      };
      await emitTo("dialogue", "capture-image-ready", payload);
      await closeCaptureWindow();
    } catch (error) {
      const payload: CaptureErrorEvent = {
        message: `Capture failed: ${String(error)}`,
      };
      await emitTo("dialogue", "capture-image-error", payload).catch(() => undefined);
      setIsCapturing(false);
      await closeCaptureWindow();
    }
  }

  async function closeCaptureWindow() {
    try {
      await invoke("close_capture_window");
      return;
    } catch (error) {
      console.debug("Native capture close command is only available inside Tauri.", error);
    }

    try {
      await getCurrentWindow().close();
    } catch (error) {
      console.debug("Capture window close is only available inside Tauri.", error);
    }
  }

  return (
    <main
      className="capture-page"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
    >
      <button
        className="capture-exit-button"
        type="button"
        aria-label="Cancel capture"
        title="Cancel capture"
        onClick={() => void closeCaptureWindow()}
        onPointerDown={(event) => event.stopPropagation()}
      >
        x
      </button>
      {activeRect && activeRect.width > 0 && activeRect.height > 0 ? (
        <div
          className="capture-selection"
          style={{
            left: activeRect.left,
            top: activeRect.top,
            width: activeRect.width,
            height: activeRect.height,
          }}
        >
          <span>
            {Math.round(activeRect.width)} x {Math.round(activeRect.height)}
          </span>
        </div>
      ) : null}
      {selectedRect ? (
        <div
          className="capture-action-panel"
          style={toolbarStyle}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            className="capture-confirm-button"
            type="button"
            disabled={isCapturing}
            onClick={() => void captureSelection(selectedRect)}
          >
            Capture
          </button>
          <button
            className="capture-cancel-button"
            type="button"
            disabled={isCapturing}
            onClick={() => setSelectedRect(null)}
          >
            Cancel
          </button>
        </div>
      ) : null}
      {isCapturing ? <div className="capture-busy" /> : null}
    </main>
  );
}
