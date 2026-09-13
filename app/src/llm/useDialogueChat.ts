import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ChatCompleteEvent,
  ChatDeltaEvent,
  ChatErrorEvent,
  ChatMessagePayload,
  ChatStreamRequest,
  DialogueMessage,
  ImagePayload,
  LlmConfigStatus,
  SendMessageOptions,
} from "./types";

const INITIAL_ASSISTANT_MESSAGE: DialogueMessage = {
  id: "initial-assistant",
  role: "assistant",
  state: "complete",
  content: "璃奈板：待机 (._.)\n我在这里。配置 API 后，就可以直接聊天。",
};

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toPayloadMessages(messages: DialogueMessage[]): ChatMessagePayload[] {
  return messages
    .filter((message) => message.id !== INITIAL_ASSISTANT_MESSAGE.id)
    .filter((message) => message.content.trim().length > 0)
    .filter((message) => message.state !== "error")
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));
}

export function useDialogueChat() {
  const [messages, setMessages] = useState<DialogueMessage[]>([INITIAL_ASSISTANT_MESSAGE]);
  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<ImagePayload[]>([]);
  const [config, setConfig] = useState<LlmConfigStatus | null>(null);
  const [status, setStatus] = useState("Checking API config...");
  const [isSending, setIsSending] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);

  const isConfigured = Boolean(config?.hasApiKey && config.model);

  const refreshConfig = useCallback(async () => {
    try {
      const nextConfig = await invoke<LlmConfigStatus>("llm_config_status");
      setConfig(nextConfig);

      if (!nextConfig.hasApiKey) {
        setStatus("API key is not configured.");
      } else if (!nextConfig.model) {
        setStatus("Model is not configured.");
      } else {
        setStatus("Ready.");
      }
    } catch (error) {
      setConfig(null);
      setStatus(`Could not read API config: ${String(error)}`);
    }
  }, []);

  useEffect(() => {
    if (isSending) return;
    let disposed=false; let off:(()=>void)|undefined;
    const refresh=()=>void refreshConfig();
    window.addEventListener('focus',refresh);
    if(isTauri())void listen('deskpet-api-config-changed',refresh).then(fn=>{if(disposed)fn();else off=fn;}).catch(console.error);
    return()=>{disposed=true;off?.();window.removeEventListener('focus',refresh);};
  }, [refreshConfig,isSending]);

  useEffect(()=>{void refreshConfig();},[refreshConfig]);

  const clearConversation = useCallback(() => {
    setMessages([INITIAL_ASSISTANT_MESSAGE]);
    setInput("");
    setPendingImages([]);
    setStatus(isConfigured ? "Ready." : "Conversation cleared. API config still needs attention.");
  }, [isConfigured]);

  const addPendingImages = useCallback((images: ImagePayload[]) => {
    if (images.length === 0) {
      return;
    }

    setPendingImages((currentImages) => [...currentImages, ...images]);
    setStatus(`${images.length} image attachment${images.length === 1 ? "" : "s"} ready.`);
  }, []);

  const removePendingImage = useCallback((index: number) => {
    setPendingImages((currentImages) => currentImages.filter((_, itemIndex) => itemIndex !== index));
  }, []);

  const clearPendingImages = useCallback(() => {
    setPendingImages([]);
  }, []);

  const sendMessage = useCallback(
    async (options: SendMessageOptions = {}) => {
      const images = options.images ?? pendingImages;
      const text = (options.text ?? input).trim();
      const messageText =
        text || (images.length > 0 ? options.fallbackText ?? "请看这张图片。" : "");

      if ((!messageText && images.length === 0) || isSending) {
        return;
      }

      if (!isConfigured) {
        setStatus("API 配置不完整，请点击璃奈板笑脸，在设置中配置。");
        return;
      }

      const requestId = createId("chat");
      const assistantId = createId("assistant");
      const userMessage: DialogueMessage = {
        id: createId("user"),
        role: "user",
        content: messageText,
        state: "complete",
        images,
      };
      const assistantMessage: DialogueMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        state: "streaming",
      };
      const nextMessages = [...messages, userMessage, assistantMessage];
      const requestMessages = toPayloadMessages([...messages, userMessage]);
      const request: ChatStreamRequest = {
        requestId,
        messages: requestMessages,
        images: images.length > 0 ? images : undefined,
      };

      setMessages(nextMessages);
      setInput("");
      setPendingImages([]);
      setIsSending(true);
      setIsStopping(false);
      setActiveRequestId(requestId);
      setStatus("Thinking...");

      const unlistenDelta = await listen<ChatDeltaEvent>("llm-chat-delta", (event) => {
        if (event.payload.requestId !== requestId) {
          return;
        }

        setMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === assistantId
              ? { ...message, content: message.content + event.payload.delta }
              : message,
          ),
        );
      });

      const unlistenComplete = await listen<ChatCompleteEvent>("llm-chat-complete", (event) => {
        if (event.payload.requestId !== requestId) {
          return;
        }

        setMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: message.content || (event.payload.status === "cancelled" ? "Stopped." : "（回复为空）"),
                  state: "complete",
                }
              : message,
          ),
        );
        setStatus(event.payload.status === "cancelled" ? "Stopped." : "Ready.");
      });

      const unlistenError = await listen<ChatErrorEvent>("llm-chat-error", (event) => {
        if (event.payload.requestId !== requestId) {
          return;
        }

        setMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: message.content || `璃奈板：困惑 (._.?)\n${event.payload.message}`,
                  state: "error",
                }
              : message,
          ),
        );
        setStatus(event.payload.message);
      });

      try {
        await invoke("chat_stream", { request });
      } catch (error) {
        const message = String(error);
        setMessages((currentMessages) =>
          currentMessages.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: item.content || `璃奈板：困惑 (._.?)\n${message}`,
                  state: "error",
                }
              : item,
          ),
        );
        setStatus(message);
      } finally {
        unlistenDelta();
        unlistenComplete();
        unlistenError();
        setIsSending(false);
        setIsStopping(false);
        setActiveRequestId(null);
      }
    },
    [input, isConfigured, isSending, messages, pendingImages],
  );

  const stopMessage = useCallback(async () => {
    if (!activeRequestId || isStopping) {
      return;
    }

    setIsStopping(true);
    setStatus("Stopping...");

    try {
      await invoke("cancel_chat_stream", { requestId: activeRequestId });
    } catch (error) {
      setIsStopping(false);
      setStatus(`Could not stop response: ${String(error)}`);
    }
  }, [activeRequestId, isStopping]);

  return useMemo(
    () => ({
      messages,
      input,
      pendingImages,
      config,
      status,
      isConfigured,
      isSending,
      isStopping,
      setInput,
      addPendingImages,
      removePendingImage,
      clearPendingImages,
      sendMessage,
      stopMessage,
      clearConversation,
      refreshConfig,
    }),
    [
      messages,
      input,
      pendingImages,
      config,
      status,
      isConfigured,
      isSending,
      isStopping,
      addPendingImages,
      removePendingImage,
      clearPendingImages,
      sendMessage,
      stopMessage,
      clearConversation,
      refreshConfig,
    ],
  );
}

