import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check, ExternalLink } from 'lucide-react';
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

function safeDomain(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return url; }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch { /* ignore */ }
      }}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs
        text-slate-500 hover:text-indigo-600 hover:bg-indigo-50
        dark:text-slate-400 dark:hover:text-indigo-300 dark:hover:bg-indigo-950/40
        transition-colors"
      aria-label="copy"
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
    </button>
  );
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
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800
          bg-gradient-to-l from-indigo-50/50 to-transparent dark:from-indigo-950/20">
          <span className="text-xl leading-none">🔍</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">بحث ويب · Web search</p>
          </div>
          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 flex items-center gap-1">
              <span className="animate-pulse">●</span>
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
            <div className="mb-4 group relative">
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap pe-8">
                {summaryAr}
              </p>
              <div className="absolute top-0 end-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <CopyButton text={summaryAr} />
              </div>
            </div>
          )}

          {/* Sources — numbered, with domain badges */}
          {sources.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3 mt-3">
              <p className="text-xs font-medium text-slate-500 mb-2">
                المصادر · {sources.length}
              </p>
              <ul className="space-y-2">
                {sources.slice(0, 6).map((src, i) => (
                  <li key={i} className="flex items-start gap-2 group">
                    <span className="flex-shrink-0 inline-flex items-center justify-center
                      w-5 h-5 rounded-full bg-slate-100 dark:bg-slate-800
                      text-[10px] font-mono font-semibold text-slate-600 dark:text-slate-400 mt-0.5">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                      >
                        <span className="truncate max-w-[420px]">{src.title || src.url}</span>
                        <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-60 transition-opacity flex-shrink-0" />
                      </a>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500">
                          {safeDomain(src.url)}
                        </span>
                      </div>
                      {src.snippet && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mt-0.5">{src.snippet}</p>
                      )}
                    </div>
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
          <div className="px-5 py-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400 flex items-center justify-between">
            <span>{t('task.elapsed', { sec: stream.elapsedSec.toFixed(1) })}</span>
            {sources.length > 0 && (
              <span className="text-[10px] font-mono opacity-60">
                {sources.length} {sources.length === 1 ? 'مصدر' : 'مصادر'}
              </span>
            )}
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
