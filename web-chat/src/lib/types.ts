// Shared message type used across ChatPage, ChatThread, and related components.
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  taskId?: string;
  pipelineId?: string;
  pipelineData?: Record<string, unknown>;
  skillHint?: string;
  timestamp: number;
}
