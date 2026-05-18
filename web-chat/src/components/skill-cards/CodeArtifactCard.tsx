import { useCallback, useEffect, useState } from 'react';
import { codeToHtml } from 'shiki';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface CodeArtifactCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

type ShikiLang =
  | 'python' | 'typescript' | 'javascript' | 'html' | 'css'
  | 'json' | 'sql' | 'bash' | 'rust' | 'go' | 'java' | 'c' | 'cpp'
  | 'yaml' | 'toml' | 'text';

const SUPPORTED_LANGS: Set<string> = new Set([
  'python', 'typescript', 'javascript', 'html', 'css', 'json',
  'sql', 'bash', 'shell', 'rust', 'go', 'java', 'c', 'cpp',
  'csharp', 'yaml', 'toml',
]);

function normalizeLanguage(lang: string): ShikiLang {
  const l = lang.toLowerCase();
  if (l === 'shell') return 'bash';
  if (l === 'csharp' || l === 'cs') return 'c';
  if (SUPPORTED_LANGS.has(l)) return l as ShikiLang;
  return 'text';
}

export function CodeArtifactCard({ taskId, goal, onSuggestion, onContinue, onEnd }: CodeArtifactCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const content = stream.skillResult?.content as string | undefined;
  const language = (stream.skillResult?.language as string | undefined) ?? 'text';
  const filename = stream.skillResult?.filename as string | undefined;
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  const [highlighted, setHighlighted] = useState<string>('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!content) return;
    const lang = normalizeLanguage(language);
    codeToHtml(content, {
      lang,
      theme: 'github-dark',
    })
      .then(setHighlighted)
      .catch(() => setHighlighted(`<pre class="shiki"><code>${content}</code></pre>`));
  }, [content, language]);

  const handleCopy = useCallback(async () => {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [content]);

  const handleDownload = useCallback(() => {
    if (!content || !filename) return;
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [content, filename]);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-violet-200 dark:border-violet-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">💻</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {filename ?? 'كود'} — <span className="font-mono">{language}</span>
            </p>
          </div>

          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
              يكتب...
            </span>
          )}
          {isDone && stream.status === 'succeeded' && (
            <div className="flex items-center gap-1">
              <button
                onClick={handleCopy}
                className="px-2 py-1 rounded text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                {copied ? '✓ تم النسخ' : 'نسخ'}
              </button>
              <button
                onClick={handleDownload}
                className="px-2 py-1 rounded text-xs bg-violet-100 text-violet-700 hover:bg-violet-200 dark:bg-violet-900/30 dark:text-violet-400 transition-colors"
              >
                ↓ تحميل
              </button>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400 px-5 py-4">
              <span className="animate-pulse text-violet-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && highlighted && (
            <div
              className="overflow-auto max-h-[500px] text-sm [&_pre]:!m-0 [&_pre]:p-5 [&_pre]:overflow-auto"
              dir="ltr"
              /* eslint-disable-next-line react/no-danger */
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
          )}

          {isDone && !highlighted && content && (
            <pre className="px-5 py-4 text-sm font-mono text-slate-700 dark:text-slate-300 overflow-auto max-h-[500px]" dir="ltr">
              {content}
            </pre>
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
