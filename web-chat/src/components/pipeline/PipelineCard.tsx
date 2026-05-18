import { useCallback } from 'react';
import { usePipeline } from '@/hooks/usePipeline';
import { PipelineStep } from './PipelineStep';
import { PipelineApproval } from './PipelineApproval';
import { PipelinePausedForm } from './PipelinePausedForm';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface PipelineCardProps {
  pipelineId: string;
  goal: string;
  initialPlan?: Record<string, unknown> | null;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const STATUS_BORDER: Record<string, string> = {
  idle:    'border-slate-200 dark:border-slate-700',
  planned: 'border-indigo-200 dark:border-indigo-800',
  running: 'border-indigo-200 dark:border-indigo-800',
  done:    'border-emerald-200 dark:border-emerald-800',
  failed:  'border-rose-200 dark:border-rose-800',
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  planned: { label: 'بانتظار الموافقة', cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' },
  running: { label: 'قيد التنفيذ',       cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  done:    { label: 'اكتمل',              cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' },
  failed:  { label: 'فشل',               cls: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400' },
};

function stepProgress(steps: { status: string }[]): string {
  if (steps.length === 0) return '';
  const done = steps.filter((s) => s.status === 'done' || s.status === 'skipped').length;
  return `${done} / ${steps.length}`;
}

export function PipelineCard({
  pipelineId,
  goal,
  initialPlan,
  onSuggestion,
  onContinue,
  onEnd,
}: PipelineCardProps) {
  const pipeline = usePipeline(pipelineId, initialPlan);
  const isDone = pipeline.status === 'done' || pipeline.status === 'failed';

  const border = STATUS_BORDER[pipeline.status] ?? STATUS_BORDER['idle']!;
  const badge = STATUS_BADGE[pipeline.status];

  const handleApproved = useCallback(() => {
    // WS will drive status to 'running' via pipeline_step_start events
  }, []);

  const handleCancelled = useCallback(() => {
    onEnd();
  }, [onEnd]);

  const handleResumed = useCallback(() => {
    // WS drives resumption
  }, []);

  const displayGoal = pipeline.goal || goal;
  const progress = stepProgress(pipeline.steps);

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${border} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🔗</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
              {displayGoal}
            </p>
            <p className="text-xs text-slate-400">
              {pipeline.summaryAr || `خطة متعددة الخطوات${progress ? ` — ${progress}` : ''}`}
            </p>
          </div>
          {badge && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${badge.cls}`}>
              {badge.label}
            </span>
          )}
        </div>

        {/* Steps list */}
        {pipeline.steps.length > 0 && (
          <div className="px-5 py-4">
            {pipeline.steps.map((step, i) => (
              <PipelineStep
                key={step.step_id}
                step={step}
                index={i}
                isLast={i === pipeline.steps.length - 1}
              />
            ))}
          </div>
        )}

        {/* Empty / loading */}
        {pipeline.steps.length === 0 && pipeline.status === 'idle' && (
          <div className="px-5 py-4 flex items-center gap-2 text-sm text-slate-400">
            <span className="animate-pulse text-indigo-400">●</span>
            <span>جارٍ تحليل الطلب…</span>
          </div>
        )}

        {/* Paused form */}
        {pipeline.paused && (
          <PipelinePausedForm
            pipelineId={pipelineId}
            stepId={pipeline.paused.step_id}
            fields={pipeline.paused.required_fields}
            onResumed={handleResumed}
          />
        )}

        {/* Approval buttons */}
        {pipeline.status === 'planned' && pipeline.needsApproval && !pipeline.paused && (
          <PipelineApproval
            pipelineId={pipelineId}
            onApproved={handleApproved}
            onCancelled={handleCancelled}
          />
        )}

        {/* Final summary */}
        {isDone && pipeline.endSummaryAr && (
          <div className={`px-5 py-3 border-t ${pipeline.status === 'done' ? 'border-emerald-100 dark:border-emerald-900/30' : 'border-rose-100 dark:border-rose-900/30'}`}>
            <p className="text-sm text-slate-700 dark:text-slate-300">{pipeline.endSummaryAr}</p>
          </div>
        )}
      </div>

      {isDone && (
        <ContinuationCard
          summaryAr={pipeline.endSummaryAr}
          verdict={pipeline.status === 'done' ? 'success' : 'failure'}
          elapsedSec={null}
          suggestions={pipeline.continuationSuggestions}
          onSuggestion={onSuggestion}
          onContinue={onContinue}
          onEnd={onEnd}
        />
      )}
    </div>
  );
}
