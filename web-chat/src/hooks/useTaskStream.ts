import { useCallback, useEffect, useReducer, useRef } from 'react';
import { makeWs } from '@/lib/api';
import type {
  AgentQuestion,
  ArtifactMeta,
  ContinuationSuggestion,
  PlanStep,
  Source,
  WsEvent,
} from '@/lib/events';
import type { TaskOutcome } from '@/lib/types';

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
  // Honest outcome from the backend (`TaskOutcome` enum). `null` means
  // legacy task without an outcome — treat as OK for back-compat.
  outcome: TaskOutcome | null;
  outcomeReason: string | null;
  /** Pending question from design agent — null when no question is active */
  pendingQuestion: AgentQuestion | null;
}

type Action =
  | { type: 'CONNECTING' }
  | { type: 'PLAN'; steps: PlanStep[] }
  | { type: 'SCREENSHOT'; screenshot: string }
  | { type: 'STEP_ADD'; step: TimelineStep }
  | { type: 'AGENT_QUESTION'; question: AgentQuestion }
  | { type: 'QUESTION_ANSWERED' }
  | { type: 'STEP_UPDATE_LAST'; patch: Partial<TimelineStep> }
  | { type: 'SOURCES'; sources: Source[] }
  | { type: 'SUGGESTIONS'; suggestions: ContinuationSuggestion[] }
  | { type: 'SKILL_RESULT'; data: Record<string, unknown> }
  | {
      type: 'DONE';
      verdict: string;
      summaryAr: string;
      elapsedSec: number | null;
      status: 'succeeded' | 'failed';
      outcome: TaskOutcome | null;
      outcomeReason: string | null;
    }
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
  outcome: null,
  outcomeReason: null,
  pendingQuestion: null,
};

function reducer(state: TaskStreamState, action: Action): TaskStreamState {
  switch (action.type) {
    case 'CONNECTING':
      return { ...state, status: 'connecting', error: null };
    case 'PLAN':
      return { ...state, plan: action.steps, status: 'running' };
    case 'AGENT_QUESTION':
      return { ...state, pendingQuestion: action.question };
    case 'QUESTION_ANSWERED':
      return { ...state, pendingQuestion: null };
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
      // Defensive: backend contracts drift; never let an undefined / non-array
      // payload land in state. A missing `sources` here used to crash the
      // chat page with "Cannot read .length of undefined" the moment
      // synthesis_done arrived → white screen until reload.
      return { ...state, sources: Array.isArray(action.sources) ? action.sources : [] };
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
        outcome: action.outcome,
        outcomeReason: action.outcomeReason,
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

      case 'synthesis_done': {
        // Older backend builds emitted `synth.to_dict()` directly (no `sources`
        // key); newer ones include `sources: Source[]`. Accept both shapes.
        const raw = (ev.data as unknown as Record<string, unknown>).sources;
        const sources = Array.isArray(raw) ? (raw as Source[]) : [];
        dispatch({ type: 'SOURCES', sources });
        break;
      }

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
        const dataAny = ev.data as unknown as Record<string, unknown>;
        const summaryAr =
          (dataAny.summary_ar as string) ??
          ev.data.summary ??
          '';
        doneRef.current = true;
        dispatch({
          type: 'DONE',
          verdict,
          summaryAr,
          elapsedSec: ev.data.elapsed_sec ?? null,
          status: verdict !== 'failure' ? 'succeeded' : 'failed',
          outcome: (dataAny.outcome as TaskOutcome | undefined) ?? null,
          outcomeReason: (dataAny.outcome_reason as string | undefined) ?? null,
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
          const dataAny = ev.data as unknown as Record<string, unknown>;
          dispatch({
            type: 'DONE',
            verdict: s === 'succeeded' ? 'success' : 'failure',
            summaryAr,
            elapsedSec: null,
            status: s === 'succeeded' ? 'succeeded' : 'failed',
            outcome: (dataAny.outcome as TaskOutcome | undefined) ?? null,
            outcomeReason: (dataAny.outcome_reason as string | undefined) ?? null,
          });
          wsRef.current?.close();
        }
        break;
      }

      case 'completion_prompt':
        dispatch({ type: 'SUGGESTIONS', suggestions: ev.data.suggestions });
        break;

      // Research-agent progress events — surfaced as timeline steps
      case 'research_round': {
        const d = ev.data as unknown as Record<string, unknown>;
        dispatch({
          type: 'STEP_ADD',
          step: { step: 0, actionType: 'search', actionLabel: `بدء جولة بحث ${d.round ?? ''}` },
        });
        break;
      }
      case 'candidate_selected': {
        const d = ev.data as unknown as Record<string, unknown>;
        dispatch({
          type: 'STEP_ADD',
          step: { step: 0, actionType: 'navigate', actionLabel: `فحص المصدر: ${d.title ?? d.url ?? ''}` },
        });
        break;
      }
      case 'content_critiqued': {
        const d = ev.data as unknown as Record<string, unknown>;
        const score = typeof d.score === 'number' ? `(${Math.round((d.score as number) * 100)}%)` : '';
        dispatch({
          type: 'STEP_UPDATE_LAST',
          patch: { ok: (d.score as number) > 0.4, note: String(d.reason ?? '') + ' ' + score },
        });
        break;
      }

      case 'agent_question':
        dispatch({ type: 'AGENT_QUESTION', question: ev.data });
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

    // Pre-flight: if the task is already finished (e.g. server restarted and
    // the in-memory event bus is empty), show the final state immediately
    // instead of opening a WS that will wait forever for events that never come.
    let cancelled = false;
    fetch(`/api/tasks/${taskId}`)
      .then((r) => r.ok ? r.json() as Promise<Record<string, unknown>> : null)
      .then((rec) => {
        if (cancelled) return;
        const status = rec?.status as string | undefined;
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') {
          doneRef.current = true;
          const result = rec?.result as Record<string, unknown> | undefined;
          const summaryAr =
            (result?.summary_ar as string | undefined) ??
            (result?.summary as string | undefined) ??
            '';
          dispatch({
            type: 'DONE',
            verdict: status === 'succeeded' ? 'success' : 'failure',
            summaryAr,
            elapsedSec: null,
            status: status === 'succeeded' ? 'succeeded' : 'failed',
            outcome: (rec?.outcome as TaskOutcome | undefined) ?? null,
            outcomeReason: (rec?.outcome_reason as string | undefined) ?? null,
          });
        } else {
          // Task still running (or not in persistent store yet) — connect WS
          connect(taskId);
        }
      })
      .catch(() => {
        // Could not reach API — attempt WS connection anyway
        if (!cancelled) connect(taskId);
      });

    return () => {
      cancelled = true;
      doneRef.current = true;
      wsRef.current?.close();
    };
  }, [taskId, connect]);

  return state;
}
