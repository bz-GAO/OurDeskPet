/** Only the original face is used as a faint watermark; the chat itself is the paper. */
export function PaperBackdrop() {
  return <svg className="dialogue-paper-backdrop" viewBox="140 195 800 1040" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false"><defs><clipPath id="paper-face-crop"><rect x="140" y="195" width="800" height="1040" /></clipPath></defs><image clipPath="url(#paper-face-crop)" href="/assets/rina/boards/paper-v3.png" x="0" y="0" width="1058" height="1486" /></svg>;
}

