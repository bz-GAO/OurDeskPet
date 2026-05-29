export type DialogueRole = "user" | "assistant";

export type DialogueMessageState = "complete" | "streaming" | "error";

export interface DialogueMessage {
  id: string;
  role: DialogueRole;
  content: string;
  state: DialogueMessageState;
  images?: ImagePayload[];
}

export interface ChatMessagePayload {
  role: DialogueRole;
  content: string;
}

export interface ImagePayload {
  mimeType: "image/png" | "image/jpeg";
  dataUrl: string;
  width?: number;
  height?: number;
  byteSize?: number;
  name?: string;
}

export interface SendMessageOptions {
  text?: string;
  images?: ImagePayload[];
  fallbackText?: string;
  source?: "chat" | "selection" | "clipboard" | "file";
}

export interface ChatStreamRequest {
  requestId: string;
  messages: ChatMessagePayload[];
  images?: ImagePayload[];
}

export interface LlmConfigStatus {
  hasApiKey: boolean;
  baseUrl: string;
  model?: string;
  modelOptions: string[];
  promptSource: string;
}

export interface ChatDeltaEvent {
  requestId: string;
  delta: string;
}

export interface ChatCompleteEvent {
  requestId: string;
}

export interface ChatErrorEvent {
  requestId: string;
  message: string;
}

export interface CaptureImageEvent {
  image: ImagePayload;
  prompt?: string;
  source: "selection";
}

export interface CaptureErrorEvent {
  message: string;
}
