import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface DesignTokensCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

interface ColorEntry {
  hex: string;
  area?: number;
  role?: string;
}

interface TokensData {
  url?: string;
  title?: string;
  colors?: Record<string, ColorEntry>;
  background_colors?: Record<string, ColorEntry>;
  fonts?: Record<string, number>;
  font_sizes?: Record<string, number>;
  border_radii?: Record<string, number>;
  summary_ar?: string;
}

function Swatch({ hex }: { hex: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="w-8 h-8 rounded-md border border-slate-200 dark:border-slate-700 shadow-sm"
        style={{ backgroundColor: hex }}
        title={hex}
      />
      <span className="text-[10px] text-slate-500 font-mono">{hex}</span>
    </div>
  );
}

export function DesignTokensCard({ taskId, goal, onSuggestion, onContinue, onEnd }: DesignTokensCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const tokens = stream.skillResult as TokensData | null;

  const topColors = Object.entries(tokens?.colors ?? {}).slice(0, 10);
  const bgColors  = Object.entries(tokens?.background_colors ?? {}).slice(0, 6);
  const fonts     = Object.entries(tokens?.fonts ?? {}).slice(0, 6);

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">🎨</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">{tokens?.title || tokens?.url || 'رموز التصميم'}</p>
          </div>
          {isDone && stream.status === 'succeeded' && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
              اكتمل
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[80px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-amber-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && tokens && (
            <div className="space-y-4">
              {/* Summary */}
              {tokens.summary_ar && (
                <p className="text-sm text-slate-700 dark:text-slate-300">{tokens.summary_ar}</p>
              )}

              {/* Primary colors */}
              {topColors.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-2">الألوان الأساسية</p>
                  <div className="flex flex-wrap gap-3">
                    {topColors.map(([hex]) => (
                      <Swatch key={hex} hex={hex} />
                    ))}
                  </div>
                </div>
              )}

              {/* Background colors */}
              {bgColors.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-2">ألوان الخلفية</p>
                  <div className="flex flex-wrap gap-3">
                    {bgColors.map(([hex]) => (
                      <Swatch key={hex} hex={hex} />
                    ))}
                  </div>
                </div>
              )}

              {/* Fonts */}
              {fonts.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-2">الخطوط</p>
                  <div className="flex flex-wrap gap-2">
                    {fonts.map(([family]) => (
                      <span
                        key={family}
                        className="px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded text-xs text-slate-700 dark:text-slate-300"
                        style={{ fontFamily: family }}
                      >
                        {family}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {isDone && !tokens && stream.summaryAr && (
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
          summaryAr={stream.summaryAr ?? tokens?.summary_ar ?? null}
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
