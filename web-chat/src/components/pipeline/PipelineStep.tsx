import { useState } from 'react';
import { useTaskStream } from '@/hooks/useTaskStream';
import type { PipelineStepState } from '@/hooks/usePipeline';

const SKILL_ICON: Record<string, string> = {
  research:        '🔍',
  summarize:       '📋',
  explore:         '🔭',
  clone:           '🧬',
  site_clone:      '🌐',
  login:           '🔐',
  signup:          '📋',
  temp_signup:     '✉️',
  design_tokens:   '🎨',
  components:      '🧩',
  find_components: '🧩',
  md_writer:       '📝',
  html_artifact:   '🌐',
  code_artifact:   '💻',
  mermaid_diagram: '📊',
  pdf_export:      '📄',
};

function StatusDot({ status }: { status: PipelineStepState['status'] }) {
  switch (status) {
    case 'running':
      return <span className="w-4 h-4 rounded-full bg-indigo-500 animate-pulse shrink-0" />;
    case 'done':
      return <span className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center shrink-0 text-[9px] text-white font-bold">✓</span>;
    case 'failed':
      return <span className="w-4 h-4 rounded-full bg-rose-500 flex items-center justify-center shrink-0 text-[9px] text-white font-bold">✗</span>;
    case 'skipped':
      return <span className="w-4 h-4 rounded-full bg-slate-300 dark:bg-slate-600 shrink-0" />;
    default:
      return <span className="w-4 h-4 rounded-full border-2 border-slate-300 dark:border-slate-600 shrink-0" />;
  }
}

interface MiniStreamProps {
  taskId: string;
}

function MiniStream({ taskId }: MiniStreamProps) {
  const stream = useTaskStream(taskId);
  if (stream.steps.length === 0) {
    return (
      <p className="text-xs text-slate-400 mt-2 px-6 animate-pulse">جارٍ التنفيذ…</p>
    );
  }
  return (
    <ul className="mt-2 px-6 space-y-0.5">
      {stream.steps.slice(-4).map((step, i) => (
        <li key={i} className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span className="shrink-0">{step.ok === true ? '✅' : step.ok === false ? '❌' : '…'}</span>
          <span className="truncate">{step.actionLabel}</span>
        </li>
      ))}
    </ul>
  );
}

interface PipelineStepProps {
  step: PipelineStepState;
  index: number;
  isLast: boolean;
}

export function PipelineStep({ step, index, isLast }: PipelineStepProps) {
  const [expanded, setExpanded] = useState(step.status === 'running');
  const icon = SKILL_ICON[step.skill] ?? '⚙️';
  const canExpand = step.status === 'running' && step.task_id;

  const statusLabel: Record<PipelineStepState['status'], string> = {
    pending: 'قيد الانتظار',
    running: 'جارٍ التنفيذ',
    done:    'اكتمل',
    failed:  'فشل',
    skipped: 'تخطّى',
  };

  const statusColor: Record<PipelineStepState['status'], string> = {
    pending: 'text-slate-400',
    running: 'text-indigo-600 dark:text-indigo-400',
    done:    'text-emerald-600 dark:text-emerald-400',
    failed:  'text-rose-600 dark:text-rose-400',
    skipped: 'text-slate-400',
  };

  return (
    <div className="relative flex flex-col">
      {/* Connector line */}
      {!isLast && (
        <div className="absolute right-[18px] top-8 bottom-0 w-px bg-slate-200 dark:bg-slate-700" />
      )}

      <div className="flex items-start gap-3 py-2">
        {/* Step number + dot */}
        <div className="flex flex-col items-center gap-1 shrink-0 w-9">
          <StatusDot status={step.status} />
          <span className="text-[10px] text-slate-400 font-mono">{index + 1}</span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-base leading-none">{icon}</span>
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1 truncate">
              {step.label_ar}
            </span>
            <span className={`text-xs shrink-0 ${statusColor[step.status]}`}>
              {statusLabel[step.status]}
            </span>
            {canExpand && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 shrink-0"
              >
                {expanded ? '▲' : '▼'}
              </button>
            )}
          </div>

          {step.error && (
            <p className="text-xs text-rose-500 mt-1 truncate">{step.error}</p>
          )}

          {expanded && step.task_id && <MiniStream taskId={step.task_id} />}
        </div>
      </div>
    </div>
  );
}
