import type { ChangeEvent, ClipboardEvent, FormEvent, KeyboardEvent } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { describeImagePayload, fileToImagePayload, isSupportedImageFile } from "../llm/imagePayload";
import type { ImagePayload } from "../llm/types";
import type { CaptureErrorEvent, CaptureImageEvent } from "../llm/types";
import { useDialogueChat } from "../llm/useDialogueChat";

import { PaperBackdrop } from './PaperBackdrop';
import './DialoguePaper.css';
import './ChatExperience.css';

const MessageMarkdown = lazy(() => import("./MessageMarkdown"));

export function DialoguePage() {
  const chat = useDialogueChat();
  const threadRef = useRef<HTMLDivElement>(null);
  const followBottom = useRef(true);
  const [awayFromBottom,setAwayFromBottom]=useState(false);
  const [confirmReset,setConfirmReset]=useState(false);
  function scrollToBottom(){const node=threadRef.current;if(node){node.scrollTop=node.scrollHeight;followBottom.current=true;setAwayFromBottom(false);}}

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

    if(followBottom.current)thread.scrollTop = thread.scrollHeight;
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

    followBottom.current=true;
    void chat.sendMessage();
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (chat.isSending) {
        return;
      }
      followBottom.current=true;
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
      chat.setStatus(`添加图片失败：${String(error)}`);
    }
  }

  function chooseImageFile() {
    fileInputRef.current?.click();
    setIsToolPanelOpen(false);
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
    <main className="dialogue-page" data-dialogue-theme="paper">
      <div className="chat-toolbar">
      <header className="dialogue-header">
        
        <div>
          <h1>Rina Dialogue</h1>
          <p>{captureStatus ?? chat.status}</p>
        </div>
        <button
          className="dialogue-clear-button"
          type="button"
          onClick={()=>setConfirmReset(true)}
        >
          重置对话
        </button>
      </header>

      {confirmReset&&<div className="chat-reset-confirm" role="alertdialog" aria-label="重置对话确认"><span>重置后将清空消息、草稿和附件{chat.isSending?'，并停止当前回复':''}。</span><button onClick={()=>{chat.clearConversation();setConfirmReset(false);followBottom.current=true;}}>确认重置</button><button onClick={()=>setConfirmReset(false)}>取消</button></div>}
      <div className="chat-options"><label>联网 <select aria-label="联网模式" value={chat.searchMode} disabled={chat.isSending} onChange={e=>chat.setSearchMode(e.target.value as 'auto'|'off'|'required')}><option value="auto">自动</option><option value="off">关闭</option><option value="required">必须搜索</option></select></label></div>
      {chat.contextNote&&<p className="chat-context-note">{chat.contextNote}</p>}
      </div>
      <section className="dialogue-shell" aria-label="Dialogue workspace">
        <section className="dialogue-main"><div className="dialogue-paper-thread-area"><PaperBackdrop />
          <div className="dialogue-thread" ref={threadRef} onScroll={e=>{const node=e.currentTarget;const near=node.scrollHeight-node.scrollTop-node.clientHeight<64;followBottom.current=near;setAwayFromBottom(!near);}}>
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
                {message.images?.length ? <button className="chat-reuse-image" type="button" onClick={()=>chat.addPendingImages(message.images!)}>再次附加这些图片</button>:null}
                <Suspense fallback={<p>{message.content}</p>}><MessageMarkdown content={message.content || (message.state === "streaming" ? "..." : "")} /></Suspense>
                {message.error&&<p className="chat-message-note" role="status">{message.error}</p>}
                {message.searchWarning&&<p className="chat-message-note">搜索未能完成查证：{message.searchWarning}</p>}
                {message.state==='cancelled'&&<p className="chat-message-note">已停止 · 部分回复不作为完整回答发送到下一轮</p>}
                {message.state==='truncated'&&<p className="chat-message-note">达到长度限制 · 回复未完整</p>}
                {message.sources?.length ? <details className="chat-sources"><summary>搜索来源（{message.sources.length}）</summary><ul>{message.sources.map(source=><li key={source.url}><a href={source.url} onClick={event=>{if(isTauri()){event.preventDefault();void openUrl(source.url).catch(error=>chat.setStatus(`打开来源失败：${String(error)}`));}}} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul></details>:null}
                {message.role==='assistant'&&message.id===chat.messages[chat.messages.length-1]?.id&&message.id!=='initial-assistant'&& !chat.isSending&&<button className="chat-retry" onClick={()=>{followBottom.current=true;void chat.retryLast();}}>{message.state==='complete'?'重新生成':'重试上一条'}</button>}
              </article>
            ))}
          </div>

          {awayFromBottom&&<button className="chat-jump-bottom" onClick={scrollToBottom}>回到最新回复 ↓</button>}
          </div><form className="dialogue-input-row" onSubmit={handleSubmit}>
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


