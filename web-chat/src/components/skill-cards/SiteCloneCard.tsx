import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface SiteCloneCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

interface PageEntry {
  url: string;
  title?: string;
  status: string;
  links_found?: number;
}

export function SiteCloneCard({ taskId, goal, onSuggestion, onContinue, onEnd }: SiteCloneCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const data = stream.skillResult as Record<string, unknown> | null;

  const success    = stream.status === 'succeeded';
  const totalPages = data?.total_pages as number | undefined;
  const outDir     = data?.out_dir     as string | undefined;
  const pages      = (data?.pages as PageEntry[] | undefined) ?? [];

  const borderColor = isDone
    ? success ? 'border-emerald-200 dark:border-emerald-800' : 'border-rose-200 dark:border-rose-800'
    : 'border-purple-200 dark:border-purple-800';

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${borderColor} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🌐</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {isDone ? `نسخ ${totalPages ?? 0} صفحة` : 'نسخ موقع كامل'}
            </p>
          </div>
          {isDone && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              success
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'
            }`}>
              {success ? 'اكتمل' : 'فشل'}
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[60px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-purple-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && success && (
            <div className="space-y-3">
              {/* Summary */}
              <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <span>✅</span>
                <span className="text-sm font-medium">
                  {data?.summary_ar as string ?? `تم نسخ ${totalPages ?? 0} صفحة`}
                </span>
              </div>

              {/* Output path */}
              {outDir && (
                <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                  <code className="text-xs font-mono text-slate-600 dark:text-slate-400 break-all">{outDir}</code>
                </div>
              )}

              {/* Pages table */}
              {pages.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-2">الصفحات المنسوخة</p>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {pages.slice(0, 20).map((pg, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className={pg.status === 'ok' ? 'text-emerald-500' : 'text-rose-400'}>
                          {pg.status === 'ok' ? '✓' : '✗'}
                        </span>
                        <span className="truncate text-slate-600 dark:text-slate-400 flex-1" title={pg.url}>
                          {pg.title || pg.url}
                        </span>
                        {pg.links_found != null && (
                          <span className="text-slate-400 shrink-0">{pg.links_found} رابط</span>
                        )}
                      </div>
                    ))}
                    {pages.length > 20 && (
                      <p className="text-xs text-slate-400">+{pages.length - 20} صفحة أخرى</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {isDone && !success && (
            <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
              <span>❌</span>
              <span className="text-sm">{stream.error || stream.summaryAr || 'فشل النسخ'}</span>
            </div>
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
