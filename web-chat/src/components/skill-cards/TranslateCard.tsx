import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface TranslateCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const LANG_LABELS: Record<string, string> = {
  ar: 'العربية',
  en: 'الإنجليزية',
  fr: 'الفرنسية',
  de: 'الألمانية',
  es: 'الإسبانية',
  zh: 'الصينية',
  tr: 'التركية',
  auto: 'تلقائي',
};

function langLabel(code: string): string {
  return LANG_LABELS[code] ?? code;
}

export function TranslateCard({ taskId, goal, onSuggestion, onContinue, onEnd }: TranslateCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const original = stream.skillResult?.original as string | undefined;
  const translated = stream.skillResult?.translated as string | undefined;
  const sourceLang = stream.skillResult?.source_lang as string | undefined;
  const targetLang = stream.skillResult?.target_lang as string | undefined;
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  // RTL langs
  const isTargetRtl = targetLang === 'ar';
  const isSourceRtl = sourceLang === 'ar';

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-sky-200 dark:border-sky-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🌐</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {sourceLang && targetLang
                ? `${langLabel(sourceLang)} ← → ${langLabel(targetLang)}`
                : 'ترجمة'}
            </p>
          </div>
          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400">
              يترجم...
            </span>
          )}
          {isDone && stream.status === 'succeeded' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              اكتمل
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-sky-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && (original || translated) && (
            <div className="grid grid-cols-2 gap-4">
              {/* Original */}
              <div className="space-y-1">
                <p className="text-xs font-medium text-slate-500">{langLabel(sourceLang ?? 'auto')}</p>
                <div
                  className="rounded-lg bg-slate-50 dark:bg-slate-800 p-3 text-sm text-slate-700 dark:text-slate-300 leading-relaxed min-h-[80px] whitespace-pre-wrap"
                  dir={isSourceRtl ? 'rtl' : 'ltr'}
                >
                  {original ?? goal}
                </div>
              </div>

              {/* Translation */}
              <div className="space-y-1">
                <p className="text-xs font-medium text-sky-600 dark:text-sky-400">{langLabel(targetLang ?? 'en')}</p>
                <div
                  className="rounded-lg bg-sky-50 dark:bg-sky-950/30 border border-sky-100 dark:border-sky-900/30 p-3 text-sm text-slate-700 dark:text-slate-300 leading-relaxed min-h-[80px] whitespace-pre-wrap"
                  dir={isTargetRtl ? 'rtl' : 'ltr'}
                >
                  {translated}
                </div>
              </div>
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
