// WebSocket event type definitions — mirrors all events the backend emits.

export type WsEventType =
  | 'perception'
  | 'plan'
  | 'decision'
  | 'action_result'
  | 'task_end'
  | 'status'
  | 'skill_result'
  | 'research_round'
  | 'candidate_selected'
  | 'content_critiqued'
  | 'synthesis_done'
  | 'pipeline_plan'
  | 'pipeline_approved'
  | 'pipeline_step_start'
  | 'pipeline_step_end'
  | 'pipeline_paused'
  | 'pipeline_resumed'
  | 'pipeline_end'
  | 'completion_prompt'
  | 'error';

export interface WsBaseEvent {
  type: WsEventType;
  task_id: string;
  tab_id?: string;
}

export interface PerceptionEvent extends WsBaseEvent {
  type: 'perception';
  data: { screenshot?: string; action_label?: string; url?: string };
}

export interface PlanStep {
  id: string;
  skill: string;
  goal: string;
}

export interface PlanEvent extends WsBaseEvent {
  type: 'plan';
  data: { steps: PlanStep[] };
}

export interface DecisionEvent extends WsBaseEvent {
  type: 'decision';
  data: { step: number; action_type: string; action_label: string; intent?: string };
}

export interface ActionResultEvent extends WsBaseEvent {
  type: 'action_result';
  data: { step: number; action_type: string; ok: boolean; note: string; screenshot?: string };
}

export interface Source {
  url: string;
  title: string;
  snippet?: string;
}

export interface TaskResult {
  summary?: string;
  sources?: Source[];
  [key: string]: unknown;
}

export interface TaskEndEvent extends WsBaseEvent {
  type: 'task_end';
  data: {
    verdict: 'success' | 'failure' | 'partial';
    reason: string;
    elapsed_sec?: number;
    summary?: string;
    result?: TaskResult;
  };
}

export interface ResearchRoundEvent extends WsBaseEvent {
  type: 'research_round';
  data: { round: number; queries: string[] };
}

export interface CandidateSelectedEvent extends WsBaseEvent {
  type: 'candidate_selected';
  data: { url: string; title: string; snippet?: string };
}

export interface ContentCritiquedEvent extends WsBaseEvent {
  type: 'content_critiqued';
  data: { url: string; score: number; reason: string };
}

export interface SynthesisDoneEvent extends WsBaseEvent {
  type: 'synthesis_done';
  data: { synthesis: string; sources: Source[] };
}

// Pipeline events

export interface PipelineStepSpec {
  step_id: string;
  skill: string;
  label_ar: string;
  fan_out?: boolean;
  depends_on?: string[];
}

export interface PipelinePlanEvent extends WsBaseEvent {
  type: 'pipeline_plan';
  data: {
    pipeline_id: string;
    goal: string;
    steps: PipelineStepSpec[];
    fan_out_cap: number;
  };
}

export interface PipelineApprovedEvent extends WsBaseEvent {
  type: 'pipeline_approved';
  data: { pipeline_id: string };
}

export interface PipelineStepStartEvent extends WsBaseEvent {
  type: 'pipeline_step_start';
  data: {
    pipeline_id: string;
    step_id: string;
    skill: string;
    task_id: string;
    fan_out_index?: number;
  };
}

export interface ArtifactMeta {
  artifact_id: string;
  kind: string;
  filename: string;
  label_ar: string;
  mime_type: string;
  size_bytes: number;
}

export interface PipelineStepEndEvent extends WsBaseEvent {
  type: 'pipeline_step_end';
  data: {
    pipeline_id: string;
    step_id: string;
    status: 'done' | 'failed' | 'skipped';
    result?: unknown;
    artifacts?: ArtifactMeta[];
  };
}

export interface RequiredField {
  name: string;
  type: 'text' | 'email' | 'password' | 'url' | 'number';
  label_ar: string;
  required: boolean;
}

export interface PipelinePausedEvent extends WsBaseEvent {
  type: 'pipeline_paused';
  data: {
    pipeline_id: string;
    step_id: string;
    reason: string;
    required_fields: RequiredField[];
  };
}

export interface PipelineResumedEvent extends WsBaseEvent {
  type: 'pipeline_resumed';
  data: { pipeline_id: string; step_id: string };
}

export interface PipelineEndEvent extends WsBaseEvent {
  type: 'pipeline_end';
  data: {
    pipeline_id: string;
    status: 'done' | 'failed';
    summary_ar: string;
    artifacts?: ArtifactMeta[];
  };
}

export interface ContinuationSuggestion {
  label_ar: string;
  prompt: string;
}

export interface CompletionPromptEvent extends WsBaseEvent {
  type: 'completion_prompt';
  data: {
    task_id?: string;
    pipeline_id?: string;
    suggestions: ContinuationSuggestion[];
  };
}

export interface WsErrorEvent extends WsBaseEvent {
  type: 'error';
  data: { message: string };
}

// skill_result — emitted after each skill finishes, carries structured result
export interface SkillResultEvent extends WsBaseEvent {
  type: 'skill_result';
  data: Record<string, unknown>;
}

// status — emitted by task_manager on task completion (succeeded/failed/cancelled)
export interface StatusEvent extends WsBaseEvent {
  type: 'status';
  data: {
    status: 'running' | 'succeeded' | 'failed' | 'cancelled';
    error?: string | null;
    result?: Record<string, unknown> | null;
  };
}

export type WsEvent =
  | PerceptionEvent
  | PlanEvent
  | DecisionEvent
  | ActionResultEvent
  | TaskEndEvent
  | ResearchRoundEvent
  | CandidateSelectedEvent
  | ContentCritiquedEvent
  | SynthesisDoneEvent
  | PipelinePlanEvent
  | PipelineApprovedEvent
  | PipelineStepStartEvent
  | PipelineStepEndEvent
  | PipelinePausedEvent
  | PipelineResumedEvent
  | PipelineEndEvent
  | CompletionPromptEvent
  | WsErrorEvent
  | SkillResultEvent
  | StatusEvent;
