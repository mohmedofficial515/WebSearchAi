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
  tokenCount?: number;
}

// Honest report of what a research task produced. Mirrors the
// `TaskOutcome` enum in src/api/tasks.py — see that file for the full
// definition. `ok` is the happy path; anything else carries an
// `outcome_reason` the UI surfaces verbatim.
export type TaskOutcome =
  | 'ok'
  | 'no_results'
  | 'partial'
  | 'search_failed'
  | 'synthesis_error';
