import type {MessageToolCall} from './toolCalls';
import type {AgentTaskCard} from './agentTasks';

export type DialogueRole = "user" | "assistant";

export type DialogueMessageState = "complete" | "streaming" | "error" | "cancelled" | "truncated";
export type SearchMode = "auto" | "off" | "required";
export type ChatMode = "chat" | "project";
export interface SearchSource { title:string; url:string; }

export interface DialogueMessage {
  id: string;
  role: DialogueRole;
  content: string;
  state: DialogueMessageState;
  images?: ImagePayload[];
  files?: ParsedFilePayload[];
  error?: string;
  sources?: SearchSource[];
  searchWarning?: string;
  toolCalls?: MessageToolCall[];
  agentTasks?: AgentTaskCard[];
  suggestsProject?: boolean;
  voice?: {dataUrl: string; text: string};
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
  sourcePath?: string;
}

export type ParsedFileKind = "text" | "code" | "document" | "spreadsheet";
export interface CodeSymbol { name:string; kind:string; line:number; }
export interface CodeFileMeta { ast:boolean; syntaxErrors:number; imports:string[]; symbols:CodeSymbol[]; }

export interface ParsedFilePayload {
  name: string;
  mimeType: string;
  byteSize: number;
  language: string;
  kind: ParsedFileKind;
  parser: string;
  content: string;
  codeMeta?: CodeFileMeta;
  sourcePath?: string;
}

export interface StoredConversation {id:string;path:string;directory:string;title:string;mode:ChatMode;revision:string;visible:boolean;}
export interface ImportedConversation {
  storage?: StoredConversation;
  path: string;
  title: string;
  mode: ChatMode;
  exportedAt: string;
  messages: Array<{
    role: DialogueRole;
    content: string;
    state: DialogueMessageState;
    files?: ParsedFilePayload[];
    sources?: SearchSource[];
    error?: string;
    searchWarning?: string;
  }>;
}

export type PendingAttachment =
  | { id:string; name:string; state:"parsing" }
  | { id:string; name:string; state:"ready"; kind:"image"; image:ImagePayload }
  | { id:string; name:string; state:"ready"; kind:"file"; file:ParsedFilePayload };

export interface SendMessageOptions {
  text?: string;
  images?: ImagePayload[];
  files?: ParsedFilePayload[];
  fallbackText?: string;
  source?: "chat" | "selection" | "clipboard" | "file";
  voiceReply?: boolean;
}

export interface ChatStreamRequest {
  requestId: string;
  messages: ChatMessagePayload[];
  images?: ImagePayload[];
  files?: ParsedFilePayload[];
  searchMode: SearchMode;
  chatMode: ChatMode;
  voiceReply?: boolean;
  currentDate: string;
  sessionId: string;
  turnId: string;
}

export interface LlmConfigStatus {
  hasApiKey: boolean;
  baseUrl: string;
  model?: string;
  modelOptions: string[];
  promptSource: string;
  searchAvailable: boolean;
  searchBackend: string;
  contextChars: number;
  searchMode: SearchMode;
  projectReadEnabled: boolean;
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
