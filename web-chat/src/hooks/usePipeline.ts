import { useCallback, useEffect, useReducer, useRef } from 'react';
import { makeWs } from '@/lib/api';
import type { ArtifactMeta, ContinuationSuggestion, RequiredField, WsEvent } from '@/lib/events';

// ── State shape ──────────────────────────────────────────────────────────────

export interface PipelineStepState {
  step_id: string;
  skill: string;
  label_ar: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  task_id?: string;
  error?: string;
}

export interface PipelinePausedInfo {
  step_id: string;
  required_fields: RequiredField[];
}

export interface PipelineState {
  status: 'idle' | 'planned' | 'running' | 'done' | 'failed';
  goal: string;
  summaryAr: string;
  needsApproval: boolean;
  steps: PipelineStepState[];
  paused: PipelinePausedInfo | null;
  endSummaryAr: string | null;
  artifacts: ArtifactMeta[];
  continuationSuggestions: ContinuationSuggestion[];
}

// ── Actions ───────────────────────────────────────────────────────────────────

type Action =
  | { type: 'INIT_PLAN'; goal: string; summaryAr: string; needsApproval: boolean; steps: PipelineStepState[] }
  | { type: 'STEP_START'; step_id: string; task_id: string }
  | { type: 'STEP_END'; step_id: string; status: 'done' | 'failed' | 'skipped'; error?: string }
  | { type: 'PAUSED'; step_id: string; required_fields: RequiredField[] }
  | { type: 'RESUMED'; step_id: string }
  | { type: 'DONE'; summaryAr: string; artifacts: ArtifactMeta[]; ok: boolean }
  | { type: 'SUGGESTIONS'; suggestions: ContinuationSuggestion[] };

const INITIAL: PipelineState = {
  status: 'idle',
  goal: '',
  summaryAr: '',
  needsApproval: false,
  steps: [],
  paused: null,
  endSummaryAr: null,
  artifacts: [],
  continuationSuggestions: [],
};

function stepFromDict(s: Record<string, unknown>): PipelineStepState {
  return {
    step_id: String(s.step_id ?? ''),
    skill: String(s.skill ?? ''),
    label_ar: String(s.label_ar ?? ''),
    status: (s.status as PipelineStepState['status']) ?? 'pending',
  };
}

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case 'INIT_PLAN':
      return {
        ...state,
        status: action.needsApproval ? 'planned' : 'running',
        goal: action.goal,
        summaryAr: action.summaryAr,
        needsApproval: action.needsApproval,
        steps: action.steps,
        paused: null,
      };
    case 'STEP_START':
      return {
        ...state,
        status: 'running',
        steps: state.steps.map((s) =>
          s.step_id === action.step_id
            ? { ...s, status: 'running', task_id: action.task_id }
            : s,
        ),
      };
    case 'STEP_END':
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.step_id === action.step_id
            ? { ...s, status: action.status, error: action.error }
            : s,
        ),
      };
    case 'PAUSED':
      return {
        ...state,
        paused: { step_id: action.step_id, required_fields: action.required_fields },
      };
    case 'RESUMED':
      return { ...state, paused: null, status: 'running' };
    case 'DONE':
      return {
        ...state,
        status: action.ok ? 'done' : 'failed',
        endSummaryAr: action.summaryAr,
        artifacts: action.artifacts,
        paused: null,
      };
    case 'SUGGESTIONS':
      return { ...state, continuationSuggestions: action.suggestions };
    default:
      return state;
  }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function usePipeline(
  pipelineId: string | null,
  initialPlan?: Record<string, unknown> | null,
): PipelineState {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const doneRef = useRef(false);
  const initializedRef = useRef(false);

  // Bootstrap from HTTP response plan so UI shows immediately (no WS round-trip)
  useEffect(() => {
    if (!initialPlan || initializedRef.current) return;
    initializedRef.current = true;
    const rawSteps = (initialPlan.steps as Record<string, unknown>[]) ?? [];
    dispatch({
      type: 'INIT_PLAN',
      goal: String(initialPlan.goal ?? ''),
      summaryAr: String(initialPlan.summary_ar ?? ''),
      needsApproval: Boolean(initialPlan.needs_approval),
      steps: rawSteps.map(stepFromDict),
    });
  }, [initialPlan]);

  const handleEvent = useCallback((ev: WsEvent) => {
    switch (ev.type) {
      case 'pipeline_plan': {
        const d = ev.data as Record<string, unknown>;
        const rawSteps = (d.steps as Record<string, unknown>[]) ?? [];
        dispatch({
          type: 'INIT_PLAN',
          goal: String(d.goal ?? ''),
          summaryAr: String(d.summary_ar ?? d.goal ?? ''),
          needsApproval: Boolean(d.needs_approval),
          steps: rawSteps.map((s) => stepFromDict(s as Record<string, unknown>)),
        });
        break;
      }
      case 'pipeline_step_start': {
        const d = ev.data as Record<string, unknown>;
        dispatch({
          type: 'STEP_START',
          step_id: String(d.step_id ?? ''),
          task_id: String(d.task_id ?? ''),
        });
        break;
      }
      case 'pipeline_step_end': {
        const d = ev.data as Record<string, unknown>;
        // Backend may send `ok: bool` (old) or `status: string` (new) — handle both.
        const rawStatus = d.status;
        const ok = d.ok;
        const stepStatus: 'done' | 'failed' | 'skipped' =
          rawStatus === 'done' || rawStatus === 'failed' || rawStatus === 'skipped'
            ? rawStatus as 'done' | 'failed' | 'skipped'
            : ok === true ? 'done' : ok === false ? 'failed' : 'done';
        dispatch({
          type: 'STEP_END',
          step_id: String(d.step_id ?? ''),
          status: stepStatus,
          error: typeof d.error === 'string' ? d.error : undefined,
        });
        break;
      }
      case 'pipeline_paused':
        dispatch({
          type: 'PAUSED',
          step_id: ev.data.step_id,
          required_fields: ev.data.required_fields,
        });
        break;
      case 'pipeline_resumed':
        dispatch({ type: 'RESUMED', step_id: ev.data.step_id });
        break;
      case 'pipeline_end': {
        doneRef.current = true;
        const d = ev.data as Record<string, unknown>;
        // Backend may send `ok: bool` (old) or `status: string` (new) — handle both.
        const isDone = d.status === 'done' || d.ok === true;
        dispatch({
          type: 'DONE',
          summaryAr: String(d.summary_ar ?? ''),
          artifacts: (d.artifacts as ArtifactMeta[]) ?? [],
          ok: isDone,
        });
        wsRef.current?.close();
        break;
      }
      case 'completion_prompt':
        dispatch({ type: 'SUGGESTIONS', suggestions: ev.data.suggestions });
        break;
      default:
        break;
    }
  }, []);

  useEffect(() => {
    if (!pipelineId) return;
    doneRef.current = false;

    const ws = makeWs(pipelineId);
    wsRef.current = ws;

    ws.onmessage = (msgEv: MessageEvent<string>) => {
      try {
        const ev = JSON.parse(msgEv.data) as WsEvent;
        handleEvent(ev);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      doneRef.current = true;
      ws.close();
    };
  }, [pipelineId, handleEvent]);

  return state;
}
