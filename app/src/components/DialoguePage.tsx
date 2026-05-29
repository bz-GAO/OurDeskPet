import type { ChangeEvent, ClipboardEvent, FormEvent, KeyboardEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { describeImagePayload, fileToImagePayload, isSupportedImageFile } from "../llm/imagePayload";
import type { ImagePayload } from "../llm/types";
import type { CaptureErrorEvent, CaptureImageEvent } from "../llm/types";
import { useDialogueChat } from "../llm/useDialogueChat";

export function DialoguePage() {
  const chat = useDialogueChat();
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isToolPanelOpen, setIsToolPanelOpen] = useState(false);
  const [previewImageIndex, setPreviewImageIndex] = useState<number | null>(null);
  const [previewSource, setPreviewSource] = useState<"pending" | "message" | null>(null);
  const [captureStatus, setCaptureStatus] = useState<string | null>(null);
  const [messagePreviewImage, setMessagePreviewImage] = useState<{
    dataUrl: string;
    alt: string;
    description?: string;
  } | null>(null);
  const addPendingImages = chat.addPendingImages;
  const setChatInput = chat.setInput;

  const pendingPreviewImage =
    previewSource === "pending" && previewImageIndex !== null
      ? chat.pendingImages[previewImageIndex]
      : null;
  const activePreviewImage =
    pendingPreviewImage
      ? {
          dataUrl: pendingPreviewImage.dataUrl,
          alt: pendingPreviewImage.name ?? "Pending image preview",
          description: describeImagePayload(pendingPreviewImage),
        }
      : messagePreviewImage;

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) {
      return;
    }

    thread.scrollTop = thread.scrollHeight;
  }, [chat.messages]);

  useEffect(() => {
    resizeInput();
  }, [chat.input]);

  useEffect(() => {
    let isMounted = true;
    let unlistenReady: (() => void) | null = null;
    let unlistenError: (() => void) | null = null;

    async function listenForCapture() {
      unlistenReady = await listen<CaptureImageEvent>("capture-image-ready", (event) => {
        if (!isMounted) {
          return;
        }

        addPendingImages([event.payload.image]);
        setChatInput((currentInput) => currentInput || event.payload.prompt || "请解释这张截图中的内容。");
        textareaRef.current?.focus();
      });

      unlistenError = await listen<CaptureErrorEvent>("capture-image-error", (event) => {
        if (!isMounted) {
          return;
        }

        console.warn(event.payload.message);
      });
    }

    void listenForCapture();

    return () => {
      isMounted = false;
      unlistenReady?.();
      unlistenError?.();
    };
  }, [addPendingImages, setChatInput]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (chat.isSending) {
      void chat.stopMessage();
      return;
    }

    void chat.sendMessage();
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (chat.isSending) {
        return;
      }
      void chat.sendMessage();
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLTextAreaElement>) {
    chat.setInput(event.target.value);
    resizeInput();
  }

  async function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    await attachImageFiles(files);
    event.target.value = "";
  }

  async function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const imageFiles = Array.from(event.clipboardData.files).filter(isSupportedImageFile);
    if (imageFiles.length === 0) {
      return;
    }

    event.preventDefault();
    await attachImageFiles(imageFiles);
  }

  async function attachImageFiles(files: File[]) {
    const imageFiles = files.filter(isSupportedImageFile);
    if (imageFiles.length === 0) {
      return;
    }

    try {
      const payloads = await Promise.all(imageFiles.map(fileToImagePayload));
      chat.addPendingImages(payloads);
    } catch (error) {
      console.warn("Failed to attach image.", error);
    }
  }

  function chooseImageFile() {
    fileInputRef.current?.click();
    setIsToolPanelOpen(false);
  }

  function prepareQuickAction(prompt: string) {
    chat.setInput(prompt);
    setIsToolPanelOpen(false);
    textareaRef.current?.focus();
  }

  async function startSystemCapture(prompt = "请解释这张截图中的内容。") {
    setIsToolPanelOpen(false);
    setCaptureStatus("Waiting for system screenshot...");
    chat.setInput((currentInput) => currentInput || prompt);

    try {
      const previousImage = await readClipboardImage();
      await invoke("start_system_screen_clip");
      await waitForClipboardScreenshot(previousImage?.dataUrl ?? null);
    } catch (error) {
      setCaptureStatus(`Capture failed: ${String(error)}`);
      console.debug("System capture is only available inside Tauri.", error);
    }
  }

  async function readClipboardImage() {
    try {
      return await invoke<ImagePayload | null>("read_clipboard_image");
    } catch {
      return null;
    }
  }

  async function waitForClipboardScreenshot(previousDataUrl: string | null) {
    const startedAt = Date.now();

    while (Date.now() - startedAt < 30000) {
      await wait(800);
      const image = await readClipboardImage();

      if (image && image.dataUrl !== previousDataUrl) {
        chat.addPendingImages([image]);
        setCaptureStatus("Screenshot attached.");
        textareaRef.current?.focus();
        window.setTimeout(() => setCaptureStatus(null), 2400);
        return;
      }
    }

    setCaptureStatus("No new screenshot detected. Paste with Ctrl+V if it is on the clipboard.");
  }

  function wait(ms: number) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function resizeInput() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 148)}px`;
  }

  return (
    <main className="dialogue-page" data-dialogue-theme="default">
      <header className="dialogue-header">
        <div>
          <h1>Rina Dialogue</h1>
          <p>{captureStatus ?? chat.status}</p>
        </div>
        <button
          className="dialogue-clear-button"
          type="button"
          onClick={chat.clearConversation}
          disabled={chat.isSending}
        >
          Clear
        </button>
      </header>

      <section className="dialogue-shell" aria-label="Dialogue workspace">
        <section className="dialogue-main">
          <div className="dialogue-thread" ref={threadRef}>
            {chat.messages.map((message) => (
              <article
                className="dialogue-message"
                data-role={message.role}
                data-state={message.state}
                key={message.id}
              >
                <span>{message.role === "user" ? "You" : "Rina"}</span>
                {message.images && message.images.length > 0 ? (
                  <div className="dialogue-message-images" aria-label="Sent image attachments">
                    {message.images.map((image, index) => (
                      <button
                        className="image-preview-button"
                        key={`${message.id}-${image.dataUrl.slice(0, 36)}-${index}`}
                        type="button"
                        onClick={() => {
                          setPreviewSource("message");
                          setPreviewImageIndex(null);
                          setMessagePreviewImage({
                            dataUrl: image.dataUrl,
                            alt: image.name ?? `Attachment ${index + 1}`,
                            description: describeImagePayload(image),
                          });
                        }}
                      >
                        <img
                          alt={image.name ?? `Attachment ${index + 1}`}
                          src={image.dataUrl}
                        />
                      </button>
                    ))}
                  </div>
                ) : null}
                <p>{message.content || (message.state === "streaming" ? "..." : "")}</p>
              </article>
            ))}
          </div>

          <form className="dialogue-input-row" onSubmit={handleSubmit}>
            <div className="dialogue-tool-area">
              <button
                className="dialogue-tool-button"
                type="button"
                aria-label="Open capture tools"
                title="Capture tools"
                onClick={() => setIsToolPanelOpen((isOpen) => !isOpen)}
              >
                <span className="capture-tool-icon" aria-hidden="true" />
              </button>
              {isToolPanelOpen ? (
                <div className="dialogue-tool-panel">
                  <button type="button" onClick={() => void startSystemCapture("请解释这张截图中的内容。")}>
                    Capture
                  </button>
                  <button type="button" onClick={() => prepareQuickAction("请解释这张图片中的内容。")}>
                    Explain
                  </button>
                  <button type="button" onClick={() => prepareQuickAction("请根据这张图片回答我的问题。")}>
                    Ask
                  </button>
                  <button type="button" onClick={() => prepareQuickAction("请总结这张图片中的重点。")}>
                    Summarize
                  </button>
                  <button type="button" onClick={chooseImageFile}>
                    Attach Image
                  </button>
                </div>
              ) : null}
            </div>

            <div className="dialogue-composer">
              {chat.pendingImages.length > 0 ? (
                <div className="pending-image-strip" aria-label="Pending image attachments">
                  {chat.pendingImages.map((image, index) => (
                    <figure className="pending-image-card" key={`${image.dataUrl.slice(0, 36)}-${index}`}>
                      <button
                        className="pending-image-preview-button"
                        type="button"
                        onClick={() => {
                          setPreviewSource("pending");
                          setPreviewImageIndex(index);
                          setMessagePreviewImage(null);
                        }}
                      >
                        <img alt={image.name ?? `Pending attachment ${index + 1}`} src={image.dataUrl} />
                      </button>
                      <figcaption>{describeImagePayload(image)}</figcaption>
                      <button
                        className="pending-image-remove-button"
                        type="button"
                        aria-label={`Remove image ${index + 1}`}
                        onClick={() => chat.removePendingImage(index)}
                      >
                        x
                      </button>
                    </figure>
                  ))}
                </div>
              ) : null}
              <textarea
                ref={textareaRef}
                placeholder={chat.isConfigured ? "Ask Rina..." : "Configure E:\\OurDeskPet\\.env first."}
                aria-label="Dialogue input"
                value={chat.input}
                onChange={handleInputChange}
                onKeyDown={handleInputKeyDown}
                onPaste={handlePaste}
                disabled={!chat.isConfigured}
                rows={1}
              />
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg"
              hidden
              onChange={handleFileInputChange}
            />
            <button
              type={chat.isSending ? "button" : "submit"}
              onClick={chat.isSending ? () => void chat.stopMessage() : undefined}
              data-mode={chat.isSending ? "stop" : "send"}
              disabled={
                (!chat.isSending && !chat.input.trim() && chat.pendingImages.length === 0) ||
                chat.isStopping ||
                !chat.isConfigured
              }
            >
              {chat.isSending ? "Stop" : "Send"}
            </button>
          </form>
        </section>
      </section>

      {activePreviewImage ? (
        <section
          className="image-preview-modal"
          aria-label="Image preview"
          role="dialog"
          onClick={() => {
            setPreviewSource(null);
            setPreviewImageIndex(null);
            setMessagePreviewImage(null);
          }}
        >
          <div className="image-preview-surface" onClick={(event) => event.stopPropagation()}>
            <button
              className="image-preview-close"
              type="button"
              aria-label="Close image preview"
              onClick={() => {
                setPreviewSource(null);
                setPreviewImageIndex(null);
                setMessagePreviewImage(null);
              }}
            >
              x
            </button>
            <img alt={activePreviewImage.alt} src={activePreviewImage.dataUrl} />
            {activePreviewImage.description ? <p>{activePreviewImage.description}</p> : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}
