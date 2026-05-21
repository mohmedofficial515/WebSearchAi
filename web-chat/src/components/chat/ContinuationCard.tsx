import { useTranslation } from 'react-i18next';
import type { ContinuationSuggestion } from '@/lib/events';

interface ContinuationCardProps {
  summaryAr: string | null;
  verdict: string | null;
  elapsedSec: number | null;
  suggestions: ContinuationSuggestion[];
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

export function ContinuationCard({
  summaryAr,
  verdict,
  elapsedSec,
  suggestions,
  onSuggestion,
  onContinue,
  onEnd,
}: ContinuationCardProps) {
  const { t } = useTranslation();
  const isSuccess = verdict !== 'failure';

  return (
    <div className={`rounded-2xl border bg-white dark:bg-slate-900 shadow-sm overflow-hidden ${
      isSuccess ? 'border-emerald-200 dark:border-emerald-800' : 'border-rose-200 dark:border-rose-800'
    }`}>
      {/* Header */}
      <div className={`px-5 py-3 flex items-center gap-3 ${
        isSuccess
          ? 'bg-gradient-to-l from-emerald-50 to-transparent dark:from-emerald-950/20'
          : 'bg-gradient-to-l from-rose-50 to-transparent dark:from-rose-950/20'
      }`}>
        <span className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm ${
          isSuccess ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'
        }`}>
          {isSuccess ? '✓' : '✗'}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            {t('continuation.title')}
          </p>
          {elapsedSec !== null && (
            <p className="text-xs text-slate-400">
              {t('task.elapsed', { sec: elapsedSec.toFixed(1) })}
            </p>
          )}
        </div>
      </div>

      {/* Summary */}
      {summaryAr && (
        <div className="px-5 py-3 text-sm text-slate-700 dark:text-slate-300 leading-relaxed border-b border-slate-100 dark:border-slate-800">
          {summaryAr}
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
            {t('continuation.suggestions')}
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onSuggestion(s.prompt)}
                className="px-3 py-1.5 rounded-xl text-xs font-medium
                  bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300
                  hover:bg-indigo-50 hover:text-indigo-700
                  dark:hover:bg-indigo-950 dark:hover:text-indigo-300
                  border border-transparent hover:border-indigo-200 dark:hover:border-indigo-800
                  transition-all"
              >
                {s.label_ar}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-5 py-3 flex gap-3">
        <button
          onClick={onContinue}
          className="flex-1 py-2 rounded-xl text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95 transition-all shadow-sm"
        >
          {t('continuation.continue')} ↩
        </button>
        <button
          onClick={onEnd}
          className="px-4 py-2 rounded-xl text-sm font-medium
            bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400
            hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-95 transition-all"
        >
          {t('continuation.end')}
        </button>
      </div>
    </div>
  );
}
