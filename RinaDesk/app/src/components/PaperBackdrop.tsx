import {BOARD} from './boardGeometry';
/** Reuse the bundled board geometry for the release watermark. */
export function PaperBackdrop() {
  return <svg className="dialogue-paper-backdrop" viewBox={BOARD.viewBox} preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false"><path d={BOARD.face} fill="currentColor"/></svg>;
}

