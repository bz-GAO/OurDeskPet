export type DialogueRole = "user" | "assistant";

export type DialogueMessageState = "complete" | "streaming" | "error" | "cancelled" | "truncated";
export type SearchMode = "auto" | "off" | "required";
export interface SearchSource { title:string; url:string; }

export interface DialogueMessage {
  id: string;
  role: DialogueRole;
  content: string;
  state: DialogueMessageState;
  images?: ImagePayload[];
  error?: string;
  sources?: SearchSource[];
  searchWarning?: string;
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
  searchMode: SearchMode;
  currentDate: string;
}

export interface LlmConfigStatus {
  hasApiKey: boolean;
  baseUrl: string;
  model?: string;
  modelOptions: string[];
  promptSource: string;
  searchAvailable: boolean;
  contextChars: number;
}

export interface ChatDeltaEvent {
  requestId: string;
  delta: string;
}

export interface ChatCompleteEvent {
  status: "completed" | "cancelled" | "truncated";
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
