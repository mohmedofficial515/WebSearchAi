import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';
import { PlanChecklist } from './PlanChecklist';

interface HtmlArtifactCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

// CSP meta tag injected into the sandbox srcDoc — per CHAT_UI_PLAN §7
const CSP_META = `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'; script-src 'none'; img-src data: blob: https:;">`;

function injectCsp(html: string): string {
  if (html.includes('<head>')) {
    return html.replace('<head>', `<head>\n  ${CSP_META}`);
  }
  return `${CSP_META}\n${html}`;
}

export function HtmlArtifactCard({ taskId, goal, onSuggestion, onContinue, onEnd }: HtmlArtifactCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const content = stream.skillResult?.content as string | undefined;
  const filename = stream.skillResult?.filename as string | undefined;
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  const safeHtml = content ? injectCsp(content) : '';

  const handleDownload = useCallback(() => {
    if (!content || !filename) return;
    const blob = new Blob([content], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [content, filename]);

  const handleOpenTab = useCallback(() => {
    if (!content) return;
    const blob = new Blob([content], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [content]);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-orange-200 dark:border-orange-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🌐</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{filename ?? 'صفحة HTML'}</p>
          </div>

          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
              يبني...
            </span>
          )}
          {isDone && stream.status === 'succeeded' && (
            <div className="flex items-center gap-1">
              <button
                onClick={handleOpenTab}
                title="فتح في تبويب جديد"
                className="px-2 py-1 rounded text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                ↗ فتح
              </button>
              <button
                onClick={handleDownload}
                title="تحميل .html"
                className="px-2 py-1 rounded text-xs bg-orange-100 text-orange-700 hover:bg-orange-200 dark:bg-orange-900/30 dark:text-orange-400 transition-colors"
              >
                ↓ .html
              </button>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-0 py-0 min-h-[80px]">
          {stream.plan && stream.plan.length > 0 && !isDone && (
            <div className="px-5 pt-4">
              <PlanChecklist
                steps={stream.plan}
                completedCount={Math.min(stream.steps.length, stream.plan.length - 1)}
                running={stream.status === 'running'}
              />
            </div>
          )}
          {!isDone && !stream.plan && (
            <div className="flex items-center gap-2 text-sm text-slate-400 px-5 py-4">
              <span className="animate-pulse text-orange-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && safeHtml && (
            <iframe
              srcDoc={safeHtml}
              title="html-preview"
              sandbox="allow-same-origin allow-forms"
              className="w-full border-0"
              style={{ height: '420px' }}
            />
          )}

          {stream.error && (
            <p className="text-sm text-rose-600 dark:text-rose-400 px-5 py-4">{stream.error}</p>
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
