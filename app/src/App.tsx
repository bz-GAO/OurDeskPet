import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { CapturePage } from "./components/CapturePage";
import { DialoguePage } from "./components/DialoguePage";
import { PetView } from "./components/PetView";
import { usePetController } from "./pet/usePetController";
import "./App.css";

function App() {
  const petController = usePetController();
  const view = new URLSearchParams(window.location.search).get("view");
  const isDialogueView = view === "dialogue";
  const isCaptureView = view === "capture";

  async function startDrag() {
    try {
      await getCurrentWindow().startDragging();
    } catch (error) {
      console.debug("Window dragging is only available inside Tauri.", error);
    }
  }

  async function minimizeWindow() {
    try {
      await getCurrentWindow().minimize();
    } catch (error) {
      console.debug("Window minimize is only available inside Tauri.", error);
    }
  }

  async function closeWindow() {
    try {
      await getCurrentWindow().close();
    } catch (error) {
      console.debug("Window close is only available inside Tauri.", error);
    }
  }

  async function openDialogueWindow() {
    try {
      const existingWindow = await WebviewWindow.getByLabel("dialogue");
      if (existingWindow) {
        await existingWindow.unminimize();
        await existingWindow.show();
        await existingWindow.setFocus();
        return;
      }

      const dialogueWindow = new WebviewWindow("dialogue", {
        url: "/?view=dialogue",
        title: "RinaDesk Agent Dialogue",
        width: 920,
        height: 680,
        minWidth: 680,
        minHeight: 500,
        resizable: true,
        decorations: true,
        center: true,
      });

      dialogueWindow.once("tauri://error", (event) => {
        console.error("Failed to open dialogue window.", event);
      });
    } catch (error) {
      console.debug("Dialogue window is only available inside Tauri.", error);
    }
  }

  if (isDialogueView) {
    return <DialoguePage />;
  }

  if (isCaptureView) {
    return <CapturePage />;
  }

  return (
    <PetView
      controller={petController}
      onStartDrag={startDrag}
      onMinimize={minimizeWindow}
      onClose={closeWindow}
      onOpenDialogue={openDialogueWindow}
    />
  );
}

export default App;
