import { useCallback, useEffect, useReducer, useRef } from 'react';
import { makeWs } from '@/lib/api';
import type {
  ArtifactMeta,
  ContinuationSuggestion,
  PlanStep,
  Source,
  WsEvent,
} from '@/lib/events';

export interface TimelineStep {
  step: number;
  actionType: string;
  actionLabel: string;
  ok?: boolean;
  note?: string;
}

export interface TaskStreamState {
  status: 'idle' | 'connecting' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  plan: PlanStep[] | null;
  steps: TimelineStep[];
  screenshot: string | null;
  verdict: string | null;
  summaryAr: string | null;
  sources: Source[];
  artifacts: ArtifactMeta[];
  continuationSuggestions: ContinuationSuggestion[];
  skillResult: Record<string, unknown> | null;
  error: string | null;
  elapsedSec: number | null;
}

type Action =
  | { type: 'CONNECTING' }
  | { type: 'PLAN'; steps: PlanStep[] }
  | { type: 'SCREENSHOT'; screenshot: string }
  | { type: 'STEP_ADD'; step: TimelineStep }
  | { type: 'STEP_UPDATE_LAST'; patch: Partial<TimelineStep> }
  | { type: 'SOURCES'; sources: Source[] }
  | { type: 'SUGGESTIONS'; suggestions: ContinuationSuggestion[] }
  | { type: 'SKILL_RESULT'; data: Record<string, unknown> }
  | { type: 'DONE'; verdict: string; summaryAr: string; elapsedSec: number | null; status: 'succeeded' | 'failed' }
  | { type: 'ERROR'; message: string }
  | { type: 'RESET' };

const INITIAL: TaskStreamState = {
  status: 'idle',
  plan: null,
  steps: [],
  screenshot: null,
  verdict: null,
  summaryAr: null,
  sources: [],
  artifacts: [],
  continuationSuggestions: [],
  skillResult: null,
  error: null,
  elapsedSec: null,
};

function reducer(state: TaskStreamState, action: Action): TaskStreamState {
  switch (action.type) {
    case 'CONNECTING':
      return { ...state, status: 'connecting', error: null };
    case 'PLAN':
      return { ...state, plan: action.steps, status: 'running' };
    case 'SCREENSHOT':
      return { ...state, screenshot: action.screenshot };
    case 'STEP_ADD':
      return { ...state, steps: [...state.steps, action.step], status: 'running' };
    case 'STEP_UPDATE_LAST': {
      if (state.steps.length === 0) return state;
      const updated = [...state.steps];
      updated[updated.length - 1] = { ...updated[updated.length - 1]!, ...action.patch };
      return { ...state, steps: updated };
    }
    case 'SOURCES':
      return { ...state, sources: action.sources };
    case 'SUGGESTIONS':
      return { ...state, continuationSuggestions: action.suggestions };
    case 'SKILL_RESULT':
      return { ...state, skillResult: action.data };
    case 'DONE':
      return {
        ...state,
        status: action.status,
        verdict: action.verdict,
        summaryAr: action.summaryAr,
        elapsedSec: action.elapsedSec,
      };
    case 'ERROR':
      return { ...state, error: action.message };
    case 'RESET':
      return INITIAL;
    default:
      return state;
  }
}

const MAX_RETRIES = 5;
const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000] as const;

export function useTaskStream(taskId: string | null): TaskStreamState {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const doneRef = useRef(false);

  const handleEvent = useCallback((ev: WsEvent) => {
    switch (ev.type) {
      case 'plan':
        dispatch({ type: 'PLAN', steps: ev.data.steps });
        break;

      case 'perception':
        if (ev.data.screenshot) dispatch({ type: 'SCREENSHOT', screenshot: ev.data.screenshot });
        if (ev.data.action_label) {
          dispatch({
            type: 'STEP_ADD',
            step: { step: 0, actionType: 'perception', actionLabel: ev.data.action_label },
          });
        }
        break;

      case 'decision':
        dispatch({
          type: 'STEP_ADD',
          step: { step: ev.data.step, actionType: ev.data.action_type, actionLabel: ev.data.action_label },
        });
        break;

      case 'action_result':
        dispatch({ type: 'STEP_UPDATE_LAST', patch: { ok: ev.data.ok, note: ev.data.note } });
        if (ev.data.screenshot) dispatch({ type: 'SCREENSHOT', screenshot: ev.data.screenshot });
        break;

      case 'synthesis_done':
        dispatch({ type: 'SOURCES', sources: ev.data.sources });
        break;

      case 'skill_result':
        dispatch({ type: 'SKILL_RESULT', data: ev.data });
        break;

      case 'task_end': {
        // Backend emits either `verdict: str` (new) or `success: bool` (legacy agent)
        const verdict =
          typeof ev.data.verdict === 'string'
            ? ev.data.verdict
            : (ev.data as unknown as Record<string, unknown>).success
            ? 'success'
            : 'failure';
        const summaryAr =
          (ev.data as unknown as Record<string, unknown>).summary_ar as string ??
          ev.data.summary ??
          '';
        doneRef.current = true;
        dispatch({
          type: 'DONE',
          verdict,
          summaryAr,
          elapsedSec: ev.data.elapsed_sec ?? null,
          status: verdict !== 'failure' ? 'succeeded' : 'failed',
        });
        wsRef.current?.close();
        break;
      }

      case 'status': {
        // Emitted by task_manager at the very end — acts as fallback task_end
        // for skills that don't go through Agent (design_tokens, site_clone, etc.)
        if (doneRef.current) break;
        const s = ev.data.status;
        if (s === 'succeeded' || s === 'failed' || s === 'cancelled') {
          doneRef.current = true;
          const result = ev.data.result;
          const summaryAr =
            (result?.summary_ar as string | undefined) ??
            (result?.summary as string | undefined) ??
            '';
          dispatch({
            type: 'DONE',
            verdict: s === 'succeeded' ? 'success' : 'failure',
            summaryAr,
            elapsedSec: null,
            status: s === 'succeeded' ? 'succeeded' : 'failed',
          });
          wsRef.current?.close();
        }
        break;
      }

      case 'completion_prompt':
        dispatch({ type: 'SUGGESTIONS', suggestions: ev.data.suggestions });
        break;

      case 'error':
        dispatch({ type: 'ERROR', message: ev.data.message });
        break;

      default:
        break;
    }
  }, []);

  const connect = useCallback(
    (id: string) => {
      if (doneRef.current) return;
      dispatch({ type: 'CONNECTING' });
      const ws = makeWs(id);
      wsRef.current = ws;

      ws.onmessage = (msgEv: MessageEvent<string>) => {
        try {
          const ev = JSON.parse(msgEv.data) as WsEvent;
          handleEvent(ev);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (doneRef.current) return;
        const attempt = retryRef.current;
        if (attempt < MAX_RETRIES) {
          retryRef.current += 1;
          setTimeout(() => connect(id), BACKOFF_MS[attempt]);
        } else {
          dispatch({ type: 'ERROR', message: 'انقطع الاتصال بعد عدة محاولات' });
        }
      };

      ws.onerror = () => ws.close();
    },
    [handleEvent],
  );

  useEffect(() => {
    if (!taskId) {
      dispatch({ type: 'RESET' });
      return;
    }
    doneRef.current = false;
    retryRef.current = 0;
    dispatch({ type: 'RESET' });
    connect(taskId);

    return () => {
      doneRef.current = true;
      wsRef.current?.close();
    };
  }, [taskId, connect]);

  return state;
}
