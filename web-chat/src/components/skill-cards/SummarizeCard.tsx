import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface SummarizeCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

export function SummarizeCard({ taskId, goal, onSuggestion, onContinue, onEnd }: SummarizeCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const summaryAr = stream.skillResult?.summary_ar as string | undefined;
  const bullets = (stream.skillResult?.bullets as string[] | undefined) ?? [];
  const originalWords = stream.skillResult?.original_word_count as number | undefined;
  const summaryWords = stream.skillResult?.summary_word_count as number | undefined;
  const ratio = originalWords && summaryWords ? Math.round((1 - summaryWords / originalWords) * 100) : null;

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">📝</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">تلخيص</p>
          </div>
          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
              يلخّص...
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
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-amber-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && summaryAr && (
            <div className="space-y-4">
              {/* Main summary */}
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                {summaryAr}
              </p>

              {/* Bullets */}
              {bullets.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-2">النقاط الرئيسية</p>
                  <ul className="space-y-1">
                    {bullets.map((b, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                        <span className="text-amber-500 mt-0.5 shrink-0">•</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Word count delta */}
              {ratio !== null && ratio > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-400 border-t border-slate-100 dark:border-slate-800 pt-3">
                  <span>📊</span>
                  <span>
                    {originalWords?.toLocaleString('ar')} كلمة → {summaryWords?.toLocaleString('ar')} كلمة
                    <span className="text-emerald-600 dark:text-emerald-400 mr-1"> (تقليص {ratio}%)</span>
                  </span>
                </div>
              )}
            </div>
          )}

          {stream.error && (
            <p className="text-sm text-rose-600 dark:text-rose-400">{stream.error}</p>
          )}
        </div>

        {stream.elapsedSec !== null && (
          <div className="px-5 py-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400">
            {t('task.elapsed', { sec: stream.elapsedSec.toFixed(1) })}
          </div>
        )}
      </div>

      {isDone && (
        <ContinuationCard
          summaryAr={summaryAr ?? stream.summaryAr}
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
