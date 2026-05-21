import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { useTaskStream } from '@/hooks/useTaskStream';
import { getSkill } from '@/lib/skills';
import { ActionIcon } from '@/components/live/ActionIcon';
import { ContinuationCard } from '@/components/chat/ContinuationCard';
import { QuestionCard } from '@/components/chat/QuestionCard';
import { PlanChecklist } from './PlanChecklist';
import type { TaskOutcome } from '@/lib/types';

interface AgentRunCardProps {
  taskId: string;
  goal: string;
  skill?: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const STATUS_BORDER: Record<string, string> = {
  idle:       'border-slate-100 dark:border-slate-800',
  connecting: 'border-amber-200 dark:border-amber-800',
  running:    'border-amber-200 dark:border-amber-800',
  succeeded:  'border-emerald-200 dark:border-emerald-800',
  failed:     'border-rose-200 dark:border-rose-800',
  cancelled:  'border-slate-200 dark:border-slate-800',
};

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  idle:       { label: '',           color: '' },
  connecting: { label: 'يتصل...',    color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  running:    { label: 'يعمل',       color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  succeeded:  { label: 'اكتمل',      color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' },
  failed:     { label: 'فشل',        color: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400' },
  cancelled:  { label: 'ملغي',       color: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
};

// Maps the honest TaskOutcome to a visual treatment. `null` and `'ok'`
// keep the existing green appearance; anything else is downgraded to
// amber (no results) or red (something actually failed).
function outcomeStyling(outcome: TaskOutcome | null): {
  border: string;
  badgeLabel: string;
  badgeColor: string;
  Icon: typeof AlertTriangle;
  iconClass: string;
} | null {
  if (outcome === null || outcome === 'ok') return null;
  if (outcome === 'no_results' || outcome === 'partial') {
    return {
      border: 'border-amber-300 dark:border-amber-700',
      badgeLabel: outcome === 'no_results' ? 'لا توجد نتائج' : 'نتيجة جزئية',
      badgeColor: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
      Icon: AlertTriangle,
      iconClass: 'text-amber-500',
    };
  }
  // search_failed / synthesis_error → red
  return {
    border: 'border-rose-300 dark:border-rose-700',
    badgeLabel: outcome === 'search_failed' ? 'فشل البحث' : 'فشل الصياغة',
    badgeColor: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
    Icon: XCircle,
    iconClass: 'text-rose-500',
  };
}

const CSP_META = `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'; script-src 'none'; img-src data: blob: https:;">`;
function injectCsp(html: string): string {
  return html.includes('<head>') ? html.replace('<head>', `<head>\n  ${CSP_META}`) : `${CSP_META}\n${html}`;
}

export function AgentRunCard({ taskId, goal, skill = 'run', onSuggestion, onContinue, onEnd }: AgentRunCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const meta = getSkill(skill);
  const htmlContent = stream.skillResult?.content as string | undefined;
  const htmlFilename = stream.skillResult?.filename as string | undefined;
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  // Outcome-driven styling wins over the raw status when the task
  // finished but didn't actually produce an answer. This is the user-
  // visible fix for "Task completed (no answer)".
  const outcomeStyle = isDone ? outcomeStyling(stream.outcome) : null;
  const defaultBadge = STATUS_BADGE[stream.status] ?? STATUS_BADGE['idle']!;
  const defaultBorder = STATUS_BORDER[stream.status] ?? STATUS_BORDER['idle']!;
  const badge = outcomeStyle
    ? { label: outcomeStyle.badgeLabel, color: outcomeStyle.badgeColor }
    : defaultBadge;
  const border = outcomeStyle?.border ?? defaultBorder;

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${border} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">{meta.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{meta.labelAr}</p>
          </div>
          {badge.label && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.color}`}>
              {badge.label}
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[60px]">
          {/* Plan checklist — shows before and during execution */}
          {stream.plan && stream.plan.length > 0 && (
            <PlanChecklist
              steps={stream.plan}
              completedCount={
                stream.status === 'succeeded' || stream.status === 'failed'
                  ? stream.plan.length
                  : Math.min(stream.steps.length, stream.plan.length - 1)
              }
              running={stream.status === 'running'}
            />
          )}

          {(stream.status === 'connecting' || (stream.status === 'running' && stream.steps.length === 0 && !stream.plan)) && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-amber-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {stream.status === 'running' && stream.steps.length > 0 && (
            <div className="space-y-1.5 border-t border-slate-100 dark:border-slate-800 pt-3 mt-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">النشاط الحالي</p>
              {stream.steps.slice(-4).map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                  <ActionIcon actionType={step.actionType} />
                  <span className="flex-1 truncate">{step.actionLabel}</span>
                  {step.ok !== undefined && (
                    <span className="text-[10px]">{step.ok ? '✓' : '✗'}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Outcome banner for NO_RESULTS / PARTIAL / SEARCH_FAILED / SYNTHESIS_ERROR */}
          {isDone && outcomeStyle && (
            <div className={`flex items-start gap-2 rounded-lg p-3 text-sm ${
              stream.outcome === 'no_results' || stream.outcome === 'partial'
                ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200'
                : 'bg-rose-50 dark:bg-rose-950/30 text-rose-900 dark:text-rose-200'
            }`}>
              <outcomeStyle.Icon className={`h-4 w-4 flex-shrink-0 mt-0.5 ${outcomeStyle.iconClass}`} />
              <span className="flex-1">
                {stream.outcomeReason || stream.summaryAr || 'لم تنتج المهمة جواباً.'}
              </span>
            </div>
          )}

          {isDone && !outcomeStyle && stream.summaryAr && (
            <p className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
              {stream.outcome === 'ok' && (
                <CheckCircle2 className="h-4 w-4 flex-shrink-0 mt-0.5 text-emerald-500" />
              )}
              <span>{stream.summaryAr}</span>
            </p>
          )}

          {/* HTML preview for design_agent output */}
          {isDone && htmlContent && (
            <div className="mt-3 border-t border-slate-100 dark:border-slate-800 pt-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-400">{htmlFilename ?? 'صفحة HTML'}</span>
                <button
                  onClick={() => {
                    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
                    window.open(URL.createObjectURL(blob), '_blank', 'noopener,noreferrer');
                  }}
                  className="text-xs px-2 py-1 rounded text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/40"
                >
                  ↗ فتح
                </button>
              </div>
              <iframe
                srcDoc={injectCsp(htmlContent)}
                title="design-preview"
                sandbox="allow-same-origin allow-forms"
                className="w-full border-0 rounded-lg overflow-hidden"
                style={{ height: '380px' }}
              />
            </div>
          )}

          {isDone && !htmlContent && stream.sources.length > 0 && (
            <ul className="mt-3 space-y-1">
              {stream.sources.slice(0, 5).map((src, i) => (
                <li key={i} className="text-xs">
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-600 dark:text-indigo-400 hover:underline truncate block"
                  >
                    {src.title || src.url}
                  </a>
                </li>
              ))}
            </ul>
          )}

          {stream.error && (
            <p className="text-sm text-rose-600 dark:text-rose-400">{stream.error}</p>
          )}
        </div>

        {/* Footer */}
        {stream.elapsedSec !== null && (
          <div className="px-5 py-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400">
            {t('task.elapsed', { sec: stream.elapsedSec.toFixed(1) })}
          </div>
        )}
      </div>

      {/* Design agent question card */}
      {stream.pendingQuestion && (
        <div className="mt-3">
          <QuestionCard
            taskId={taskId}
            question={stream.pendingQuestion}
            onAnswered={() => { /* WS will send next question or continue */ }}
          />
        </div>
      )}

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
