import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface ExploreReportCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

const TABS = [
  { key: 'executive_summary', label: 'ملخص تنفيذي' },
  { key: 'features',          label: 'المميزات' },
  { key: 'ux_notes',          label: 'تجربة المستخدم' },
  { key: 'pages',             label: 'الصفحات' },
  { key: 'recommendations',   label: 'التوصيات' },
] as const;

type TabKey = typeof TABS[number]['key'];

export function ExploreReportCard({ taskId, goal, onSuggestion, onContinue, onEnd }: ExploreReportCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const [activeTab, setActiveTab] = useState<TabKey>('executive_summary');

  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const report = stream.skillResult?.report as Record<string, unknown> | undefined;
  const site = stream.skillResult?.site as string | undefined;

  const renderSection = (key: TabKey) => {
    if (!report) return null;
    const val = report[key];
    if (!val) return <p className="text-sm text-slate-400">لا توجد بيانات</p>;
    if (Array.isArray(val)) {
      return (
        <ul className="space-y-1 list-disc list-inside">
          {(val as unknown[]).map((item, i) => (
            <li key={i} className="text-sm text-slate-700 dark:text-slate-300">
              {typeof item === 'string' ? item : JSON.stringify(item)}
            </li>
          ))}
        </ul>
      );
    }
    return <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{String(val)}</p>;
  };

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-violet-200 dark:border-violet-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🔭</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{site ? `استكشاف ${site}` : 'استكشاف موقع'}</p>
          </div>
          {isDone && stream.status === 'succeeded' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
              اكتمل
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-violet-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && report && (
            <>
              {/* Tab bar */}
              <div className="flex gap-1 overflow-x-auto pb-2 mb-4 border-b border-slate-100 dark:border-slate-800">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      activeTab === tab.key
                        ? 'bg-violet-600 text-white'
                        : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              {/* Tab content */}
              <div>{renderSection(activeTab)}</div>
            </>
          )}

          {isDone && !report && stream.summaryAr && (
            <p className="text-sm text-slate-700 dark:text-slate-300">{stream.summaryAr}</p>
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
