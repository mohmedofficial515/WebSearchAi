import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { getSkill } from '@/lib/skills';
import { ActionIcon } from '@/components/live/ActionIcon';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface AgentRunCardProps {
  taskId: string;
  goal: string;
  skill?: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const STATUS_BORDER: Record<string, string> = {
  idle:       'border-slate-100 dark:border-slate-800',
  connecting: 'border-amber-200 dark:border-amber-800',
  running:    'border-amber-200 dark:border-amber-800',
  succeeded:  'border-emerald-200 dark:border-emerald-800',
  failed:     'border-rose-200 dark:border-rose-800',
  cancelled:  'border-slate-200 dark:border-slate-800',
};

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  idle:       { label: '',           color: '' },
  connecting: { label: 'يتصل...',    color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  running:    { label: 'يعمل',       color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  succeeded:  { label: 'اكتمل',      color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' },
  failed:     { label: 'فشل',        color: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400' },
  cancelled:  { label: 'ملغي',       color: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
};

export function AgentRunCard({ taskId, goal, skill = 'run', onSuggestion, onContinue, onEnd }: AgentRunCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const meta = getSkill(skill);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const badge = STATUS_BADGE[stream.status] ?? STATUS_BADGE['idle']!;
  const border = STATUS_BORDER[stream.status] ?? STATUS_BORDER['idle']!;

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${border} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">{meta.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{meta.labelAr}</p>
          </div>
          {badge.label && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.color}`}>
              {badge.label}
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[60px]">
          {(stream.status === 'connecting' || (stream.status === 'running' && stream.steps.length === 0)) && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-amber-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {stream.status === 'running' && stream.steps.length > 0 && (
            <div className="space-y-2">
              {stream.steps.slice(-4).map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <ActionIcon actionType={step.actionType} />
                  <span className="flex-1 truncate">{step.actionLabel}</span>
                  {step.ok !== undefined && (
                    <span>{step.ok ? '✅' : '❌'}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {isDone && stream.summaryAr && (
            <p className="text-sm text-slate-700 dark:text-slate-300">{stream.summaryAr}</p>
          )}

          {isDone && stream.sources.length > 0 && (
            <ul className="mt-3 space-y-1">
              {stream.sources.slice(0, 5).map((src, i) => (
                <li key={i} className="text-xs">
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-600 dark:text-indigo-400 hover:underline truncate block"
                  >
                    {src.title || src.url}
                  </a>
                </li>
              ))}
            </ul>
          )}

          {stream.error && (
            <p className="text-sm text-rose-600 dark:text-rose-400">{stream.error}</p>
          )}
        </div>

        {/* Footer */}
        {stream.elapsedSec !== null && (
          <div className="px-5 py-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400">
            {t('task.elapsed', { sec: stream.elapsedSec.toFixed(1) })}
          </div>
        )}
      </div>

      {isDone && (
        <ContinuationCard
          summaryAr={stream.summaryAr}
          verdict={stream.verdict}
          elapsedSec={stream.elapsedSec}
          suggestions={stream.continuationSuggestions}
          onSuggestion={onSuggestion}
          onContinue={onContinue}
          onEnd={onEnd}
        />
      )}
    </div>
  );
}
