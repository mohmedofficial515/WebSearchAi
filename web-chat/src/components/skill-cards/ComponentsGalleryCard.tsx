import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface ComponentsGalleryCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

interface Variant {
  source_url?: string;
  jsx_code?: string;
  html_code?: string;
  description_ar?: string;
  preview_path?: string;
}

interface ComponentResult {
  query?: string;
  total_variants?: number;
  variants?: Variant[];
  viewer_path?: string;
  summary_ar?: string;
}

export function ComponentsGalleryCard({ taskId, goal, onSuggestion, onContinue, onEnd }: ComponentsGalleryCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const [selected, setSelected] = useState(0);
  const [tab, setTab] = useState<'jsx' | 'html'>('jsx');

  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const data = stream.skillResult as ComponentResult | null;
  const variants = data?.variants ?? [];

  const current = variants[selected];

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-cyan-200 dark:border-cyan-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🧩</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {isDone ? `${data?.total_variants ?? 0} مكون` : 'مكونات واجهة'}
            </p>
          </div>
          {isDone && stream.status === 'succeeded' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400">
              اكتمل
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-cyan-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && variants.length > 0 && (
            <div className="space-y-3">
              {/* Variant selector */}
              {variants.length > 1 && (
                <div className="flex flex-wrap gap-1">
                  {variants.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setSelected(i)}
                      className={`px-2 py-0.5 rounded text-xs transition-colors ${
                        selected === i
                          ? 'bg-cyan-600 text-white'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                      }`}
                    >
                      {i + 1}
                    </button>
                  ))}
                </div>
              )}

              {current && (
                <>
                  {current.description_ar && (
                    <p className="text-sm text-slate-600 dark:text-slate-400">{current.description_ar}</p>
                  )}

                  {/* Code tab switcher */}
                  <div className="flex gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
                    {current.jsx_code && (
                      <button
                        onClick={() => setTab('jsx')}
                        className={`text-xs px-2 py-0.5 rounded ${tab === 'jsx' ? 'bg-slate-200 dark:bg-slate-700 font-medium' : 'text-slate-400'}`}
                      >
                        JSX
                      </button>
                    )}
                    {current.html_code && (
                      <button
                        onClick={() => setTab('html')}
                        className={`text-xs px-2 py-0.5 rounded ${tab === 'html' ? 'bg-slate-200 dark:bg-slate-700 font-medium' : 'text-slate-400'}`}
                      >
                        HTML
                      </button>
                    )}
                  </div>

                  <pre className="bg-slate-950 text-slate-100 rounded-lg p-3 text-xs overflow-x-auto max-h-48 font-mono">
                    <code>{tab === 'jsx' ? current.jsx_code : current.html_code}</code>
                  </pre>

                  {current.source_url && (
                    <a
                      href={current.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      المصدر ↗
                    </a>
                  )}
                </>
              )}
            </div>
          )}

          {isDone && variants.length === 0 && (
            <p className="text-sm text-slate-500">{stream.summaryAr || 'لم يتم العثور على مكونات'}</p>
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
          summaryAr={stream.summaryAr ?? data?.summary_ar ?? null}
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
