import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface CompetitorMatrixCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

type SortDir = 'asc' | 'desc';

export function CompetitorMatrixCard({ taskId, goal, onSuggestion, onContinue, onEnd }: CompetitorMatrixCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';

  const competitors = (stream.skillResult?.competitors as string[] | undefined) ?? [];
  const features = (stream.skillResult?.features as string[] | undefined) ?? [];
  const matrix = (stream.skillResult?.matrix as Record<string, string>[] | undefined) ?? [];
  const csvContent = stream.skillResult?.csv_content as string | undefined;
  const filename = stream.skillResult?.filename as string | undefined;
  const summaryAr = stream.skillResult?.summary_ar as string | undefined;

  const [sortCol, setSortCol] = useState<string>('');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [filter, setFilter] = useState('');

  const handleSort = useCallback((col: string) => {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }, [sortCol]);

  const filteredMatrix = matrix.filter((row) => {
    if (!filter) return true;
    return Object.values(row).some((v) => String(v).includes(filter));
  });

  const sortedMatrix = [...filteredMatrix].sort((a, b) => {
    if (!sortCol) return 0;
    const av = String(a[sortCol] ?? '');
    const bv = String(b[sortCol] ?? '');
    const cmp = av.localeCompare(bv, 'ar');
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const handleDownloadCsv = useCallback(() => {
    if (!csvContent || !filename) return;
    const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [csvContent, filename]);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🏆</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">
              {competitors.length > 0
                ? `${competitors.length} منافس × ${features.length} معيار`
                : 'مصفوفة مقارنة'}
            </p>
          </div>

          {stream.status === 'running' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400">
              يحلل...
            </span>
          )}
          {isDone && matrix.length > 0 && (
            <button
              onClick={handleDownloadCsv}
              className="px-2 py-1 rounded text-xs bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-400 transition-colors"
            >
              ↓ CSV
            </button>
          )}
        </div>

        {/* Filter */}
        {isDone && matrix.length > 0 && (
          <div className="px-5 pt-3">
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="تصفية..."
              className="w-full max-w-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
          </div>
        )}

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-indigo-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && sortedMatrix.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse" dir="rtl">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th
                      className="text-start px-3 py-2 font-medium text-slate-600 dark:text-slate-400 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 select-none whitespace-nowrap"
                      onClick={() => handleSort('competitor')}
                    >
                      المنافس {sortCol === 'competitor' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                    </th>
                    {features.map((f) => (
                      <th
                        key={f}
                        className="text-start px-3 py-2 font-medium text-slate-600 dark:text-slate-400 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 select-none whitespace-nowrap"
                        onClick={() => handleSort(f)}
                      >
                        {f} {sortCol === f ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedMatrix.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <td className="px-3 py-2 font-medium text-slate-800 dark:text-slate-200 whitespace-nowrap">
                        {row['competitor']}
                      </td>
                      {features.map((f) => (
                        <td key={f} className="px-3 py-2 text-slate-600 dark:text-slate-400">
                          {row[f] ?? '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {isDone && sortedMatrix.length === 0 && !stream.error && (
            <p className="text-sm text-slate-400">لا توجد بيانات</p>
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
