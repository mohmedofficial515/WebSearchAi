import { useCallback, useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface MermaidArtifactCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

mermaid.initialize({ startOnLoad: false, theme: 'neutral', fontFamily: 'Tajawal, Inter, sans-serif' });

let diagramCounter = 0;

export function MermaidArtifactCard({ taskId, goal, onSuggestion, onContinue, onEnd }: MermaidArtifactCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const content = stream.skillResult?.content as string | undefined;
  const diagramType = (stream.skillResult?.diagram_type as string | undefined) ?? 'مخطط';
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  const [svg, setSvg] = useState<string>('');
  const [renderError, setRenderError] = useState<string>('');
  const idRef = useRef(`mmd-${++diagramCounter}`);

  useEffect(() => {
    if (!content) return;
    setSvg('');
    setRenderError('');
    mermaid
      .render(idRef.current, content)
      .then(({ svg: rendered }) => setSvg(rendered))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setRenderError(`خطأ في رسم المخطط: ${msg}`);
      });
    // regenerate id for next render to avoid mermaid caching issues
    idRef.current = `mmd-${++diagramCounter}`;
  }, [content]);

  const handleDownloadSvg = useCallback(() => {
    if (!svg) return;
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `diagram-${Date.now()}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }, [svg]);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-teal-200 dark:border-teal-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">📊</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{diagramType}</p>
          </div>

          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400">
              يرسم...
            </span>
          )}
          {isDone && svg && (
            <button
              onClick={handleDownloadSvg}
              className="px-2 py-1 rounded text-xs bg-teal-100 text-teal-700 hover:bg-teal-200 dark:bg-teal-900/30 dark:text-teal-400 transition-colors"
            >
              ↓ SVG
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-teal-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && renderError && (
            <div className="space-y-2">
              <p className="text-sm text-rose-600 dark:text-rose-400">{renderError}</p>
              {content && (
                <pre className="text-xs font-mono text-slate-500 overflow-auto max-h-[200px] bg-slate-50 dark:bg-slate-800 rounded p-2" dir="ltr">
                  {content}
                </pre>
              )}
            </div>
          )}

          {svg && (
            <div
              className="overflow-auto max-h-[500px] flex justify-center [&_svg]:max-w-full"
              /* eslint-disable-next-line react/no-danger */
              dangerouslySetInnerHTML={{ __html: svg }}
            />
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
