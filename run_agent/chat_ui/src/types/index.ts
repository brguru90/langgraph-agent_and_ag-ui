// Type definitions for the chat application

import type {
  BaseEvent,
  RunErrorEvent,
  RunStartedEvent,
  TextMessageStartEvent,
  TextMessageContentEvent,
  TextMessageEndEvent,
  ToolCallStartEvent,
  ToolCallArgsEvent,
  ToolCallEndEvent,
  ToolCallResultEvent,
  StateDeltaEvent,
  StateSnapshotEvent,
  CustomEvent,
  RawEvent,
} from "@ag-ui/client";

export interface LangGraphMessage {
  id: string;
  type: "human" | "ai" | "tool" | "system";
  content: string | ContentItem[];
  tool_call_id?: string;
  name?: string | null;
  example?: boolean;
  additional_kwargs?: Record<string, unknown>;
  response_metadata?: ResponseMetadata;
  tool_calls?: ToolCall[];
  invalid_tool_calls?: unknown[];
  usage_metadata?: UsageMetadata;
  artifact?: unknown;
  status?: string;
}

export interface TokenUsage {
  totalInput: number;
  totalOutput: number;
  totalTokens: number;
}

export interface ChatDisplayMessage {
  id: string | number;
  message_type: "assistance" | "tool" | "interrupt" | "user" | "code";
  block: "start" | "end" | "content";
  content?: string;
  tokenUsage?: TokenUsage;
  toolCalls?: {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }[];
  interruptData?: {
    question: string;
    isActive: boolean;
    response?: "yes" | "no" | string;
  };
  codeData?: {
    message_id: string;
    codeContent?: CodeContent;
  };
}

export interface CodeSnippet {
  code: string;
  file_name: string;
  language: string;
  framework: string;
  pluggable_live_preview_component?: string;
  descriptions: string[];
}

export interface CodeContent {
  code_snippets: CodeSnippet[];
  descriptions: string[];
}

export interface GroupedChatDisplayMessage {
 id: string | number;
 messages: ChatDisplayMessage[];
 group_type:ChatDisplayMessage['message_type']
 partial: boolean;
}

export interface InterruptPrompt {
  id: string;
  message: string;
  isActive: boolean;
  onSubmit: (response: string) => void;
  onCancel: () => void;
}

export interface ContentItem {
  type: "text" | "tool_use";
  text?: string;
  id?: string;
  name?: string;
  index?: number;
  input?: string | Record<string, unknown>;
}

export interface ResponseMetadata {
  stopReason?: string;
  metrics?: {
    latencyMs: number;
  };
  model_name?: string;
  ResponseMetadata?: {
    RequestId: string;
    HTTPStatusCode: number;
    HTTPHeaders: Record<string, string>;
    RetryAttempts: number;
  };
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  id: string;
  type: string;
}

export interface UsageMetadata {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_token_details?: {
    cache_creation: number;
    cache_read: number;
  };
}

export interface ChatThread {
  id: string;
  title: string;
  createdAt: Date;
  lastMessageAt: Date;
  messageCount: number;
}

export interface ChatMessage {
  id: string;
  threadId: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
}

export interface ChatHistoryResponse {
  threads: ChatThread[];
}

export interface ThreadMessagesResponse {
  messages: ChatMessage[];
}

export interface RunData {
  runId: string;
  forwardedProps?: {
    user_id: string;
    command?: {
      resume: string;
    };
    node_name?: "route" | "llm" | "tool"
  };
}

export type MessageEvent =
  | BaseEvent
  | RunStartedEvent
  | RunErrorEvent
  | TextMessageStartEvent
  | TextMessageContentEvent
  | TextMessageEndEvent
  | ToolCallStartEvent
  | ToolCallArgsEvent
  | ToolCallEndEvent
  | ToolCallResultEvent
  | StateDeltaEvent
  | StateSnapshotEvent
  | CustomEvent
  | RawEvent;

export const INTERRUPT_EVENT = "agent-interrupt";
