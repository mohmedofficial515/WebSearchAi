import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';
import { ActionIcon } from '@/components/live/ActionIcon';

interface SearchResultCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const STATUS_BORDER: Record<string, string> = {
  idle:       'border-slate-100 dark:border-slate-800',
  connecting: 'border-indigo-200 dark:border-indigo-800',
  running:    'border-indigo-200 dark:border-indigo-800',
  succeeded:  'border-emerald-200 dark:border-emerald-800',
  failed:     'border-rose-200 dark:border-rose-800',
  cancelled:  'border-slate-200 dark:border-slate-800',
};

interface Source {
  url: string;
  title?: string;
  snippet?: string;
}

export function SearchResultCard({ taskId, goal, onSuggestion, onContinue, onEnd }: SearchResultCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const border = STATUS_BORDER[stream.status] ?? STATUS_BORDER['idle']!;

  const sources: Source[] = stream.sources.length > 0
    ? stream.sources
    : ((stream.skillResult?.sources as Source[] | undefined) ?? []);

  const summaryAr = stream.summaryAr
    ?? (stream.skillResult?.summary_ar as string | undefined)
    ?? '';

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${border} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🔍</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">بحث ويب</p>
          </div>
          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
              يبحث...
            </span>
          )}
          {isDone && stream.status === 'succeeded' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              اكتمل
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[60px]">
          {/* Running steps */}
          {stream.status === 'running' && stream.steps.length > 0 && (
            <div className="space-y-2 mb-3">
              {stream.steps.slice(-3).map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <ActionIcon actionType={step.actionType} />
                  <span className="flex-1 truncate">{step.actionLabel}</span>
                  {step.ok !== undefined && <span>{step.ok ? '✅' : '❌'}</span>}
                </div>
              ))}
            </div>
          )}

          {(stream.status === 'connecting' || (stream.status === 'running' && stream.steps.length === 0)) && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-indigo-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {/* Arabic synthesis summary */}
          {isDone && summaryAr && (
            <div className="mb-4">
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
                {summaryAr}
              </p>
            </div>
          )}

          {/* Sources */}
          {sources.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3 mt-3">
              <p className="text-xs font-medium text-slate-500 mb-2">المصادر</p>
              <ul className="space-y-2">
                {sources.slice(0, 6).map((src, i) => (
                  <li key={i} className="flex flex-col gap-0.5">
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline truncate block font-medium"
                    >
                      {src.title || src.url}
                    </a>
                    {src.snippet && (
                      <p className="text-xs text-slate-500 line-clamp-2">{src.snippet}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
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
          summaryAr={summaryAr}
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
