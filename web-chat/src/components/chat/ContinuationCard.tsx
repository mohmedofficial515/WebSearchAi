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
    <div className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
      {/* Header */}
      <div className={`px-5 py-3 flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 ${
        isSuccess ? 'bg-emerald-50 dark:bg-emerald-950/30' : 'bg-rose-50 dark:bg-rose-950/30'
      }`}>
        <span className="text-lg">{isSuccess ? '✅' : '❌'}</span>
        <span className="font-medium text-sm text-slate-800 dark:text-slate-200">
          {t('continuation.title')}
        </span>
        {elapsedSec !== null && (
          <span className="text-xs text-slate-400 me-auto">
            {t('task.elapsed', { sec: elapsedSec.toFixed(1) })}
          </span>
        )}
      </div>

      {/* Summary */}
      {summaryAr && (
        <div className="px-5 py-3 text-sm text-slate-700 dark:text-slate-300 border-b border-slate-100 dark:border-slate-800">
          {summaryAr}
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="px-5 py-3">
          <p className="text-xs font-medium text-slate-400 mb-2">{t('continuation.suggestions')}</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onSuggestion(s.prompt)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800
                  text-slate-700 dark:text-slate-300 hover:bg-indigo-50 hover:text-indigo-700
                  dark:hover:bg-indigo-950 dark:hover:text-indigo-300 transition-colors"
              >
                {s.label_ar}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-5 py-3 flex gap-3 border-t border-slate-100 dark:border-slate-800">
        <button
          onClick={onContinue}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
        >
          {t('continuation.continue')} ↩
        </button>
        <button
          onClick={onEnd}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-slate-100 dark:bg-slate-800
            text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          {t('continuation.end')} ✕
        </button>
      </div>
    </div>
  );
}
