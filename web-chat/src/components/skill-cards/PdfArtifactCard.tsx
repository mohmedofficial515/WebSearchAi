import { useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface PdfArtifactCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

export function PdfArtifactCard({ taskId, goal, onSuggestion, onContinue, onEnd }: PdfArtifactCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const content = stream.skillResult?.content as string | undefined;
  const filename = stream.skillResult?.filename as string | undefined;
  const wordCount = stream.skillResult?.word_count as number | undefined;
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  // Client-side print-to-PDF via browser dialog
  const handlePrint = useCallback(() => {
    if (!content) return;
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;
    printWindow.document.write(`<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="UTF-8">
  <title>${goal}</title>
  <style>
    body { font-family: 'Tajawal', Arial, sans-serif; direction: rtl; padding: 2cm; line-height: 1.8; color: #1a1a1a; }
    h1,h2,h3 { color: #2d2d2d; } table { width: 100%; border-collapse: collapse; }
    td, th { border: 1px solid #ccc; padding: 6px 10px; }
    @media print { body { padding: 1cm; } }
  </style>
</head>
<body><pre style="white-space:pre-wrap;font-family:inherit">${content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></body>
</html>`);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  }, [content, goal]);

  const handleDownloadMd = useCallback(() => {
    if (!content || !filename) return;
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [content, filename]);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-red-200 dark:border-red-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">📑</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {filename ?? 'مستند PDF'}
              {wordCount ? ` — ${wordCount.toLocaleString('ar')} كلمة` : ''}
            </p>
          </div>

          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
              يولّد...
            </span>
          )}
          {isDone && stream.status === 'succeeded' && (
            <div className="flex items-center gap-1">
              <button
                onClick={handleDownloadMd}
                className="px-2 py-1 rounded text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                ↓ .md
              </button>
              <button
                onClick={handlePrint}
                className="px-2 py-1 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 transition-colors"
              >
                🖨 PDF
              </button>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-red-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && content && (
            <div className="prose prose-sm prose-slate dark:prose-invert max-w-none overflow-auto max-h-[500px]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
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
