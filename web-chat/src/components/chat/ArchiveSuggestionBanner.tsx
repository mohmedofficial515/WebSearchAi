import { useTranslation } from 'react-i18next';
import type { ArchiveSuggestion } from '@/hooks/useArchiveSuggestion';

interface ArchiveSuggestionBannerProps {
  suggestion: ArchiveSuggestion;
  onUse: () => void;
  onDismiss: () => void;
}

export function ArchiveSuggestionBanner({ suggestion, onUse, onDismiss }: ArchiveSuggestionBannerProps) {
  const { t } = useTranslation();
  const pct = Math.round(suggestion.score * 100);

  return (
    <div className="mx-4 mb-1 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-4 py-3">
      <div className="flex items-start gap-3">
        <span className="text-amber-500 text-lg leading-none flex-shrink-0">📦</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
              {t('archiveSuggestion.found')}
            </span>
            <span className="text-xs text-amber-600 dark:text-amber-500 bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 rounded">
              {t('archiveSuggestion.score', { pct })}
            </span>
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-300 mt-0.5 line-clamp-1">
            {suggestion.goal}
          </p>
          {suggestion.summary && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
              {suggestion.summary}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={onUse}
            className="px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-500 text-white hover:bg-amber-600 transition-colors"
          >
            {t('archiveSuggestion.use')}
          </button>
          <button
            onClick={onDismiss}
            className="px-2 py-1 rounded-lg text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {t('archiveSuggestion.dismiss')}
          </button>
        </div>
      </div>
    </div>
  );
}
