// Shared message type used across ChatPage, ChatThread, and related components.
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  taskId?: string;
  pipelineId?: string;
  skillHint?: string;
  timestamp: number;
}
