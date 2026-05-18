import { useTranslation } from 'react-i18next';
import { useTaskStream } from '@/hooks/useTaskStream';
import { ContinuationCard } from '@/components/chat/ContinuationCard';

interface TempSignupCardProps {
  taskId: string;
  goal: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

export function TempSignupCard({ taskId, goal, onSuggestion, onContinue, onEnd }: TempSignupCardProps) {
  const { t } = useTranslation();
  const stream = useTaskStream(taskId);
  const isDone = stream.status === 'succeeded' || stream.status === 'failed';
  const data = stream.skillResult as Record<string, unknown> | null;

  const success     = stream.status === 'succeeded';
  const email       = data?.email        as string | undefined;
  const password    = data?.password     as string | undefined;
  const profileName = data?.profile_name as string | undefined;
  const verified    = data?.verified     as boolean | undefined;

  const borderColor = isDone
    ? success ? 'border-emerald-200 dark:border-emerald-800' : 'border-rose-200 dark:border-rose-800'
    : 'border-sky-200 dark:border-sky-800';

  return (
    <div className="space-y-3">
      <div className={`rounded-2xl border ${borderColor} bg-white dark:bg-slate-900 shadow-sm overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl leading-none">✉️</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{goal}</p>
            <p className="text-xs text-slate-400">تسجيل مؤقت + جلسة دائمة</p>
          </div>
          {isDone && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              success
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'
            }`}>
              {success ? 'تم الحفظ' : 'فشل'}
            </span>
          )}
        </div>

        {/* Body */}
        <div className="px-5 py-4 min-h-[60px]">
          {!isDone && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse text-sky-400">●</span>
              <span>{t('task.running')}</span>
            </div>
          )}

          {isDone && success && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <span>✅</span>
                <span className="text-sm font-medium">
                  {verified ? 'تم التحقق وحفظ الجلسة' : 'تم التسجيل وحفظ الجلسة'}
                </span>
              </div>
              {(email || password || profileName) && (
                <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3 space-y-1.5">
                  {profileName && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-slate-400 min-w-[70px]">الملف:</span>
                      <code className="text-slate-700 dark:text-slate-200 font-mono text-xs">{profileName}</code>
                    </div>
                  )}
                  {email && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-slate-400 min-w-[70px]">البريد:</span>
                      <code className="text-slate-700 dark:text-slate-200 font-mono text-xs">{email}</code>
                    </div>
                  )}
                  {password && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-slate-400 min-w-[70px]">كلمة المرور:</span>
                      <code className="text-slate-700 dark:text-slate-200 font-mono text-xs">{password}</code>
                    </div>
                  )}
                </div>
              )}
              {stream.summaryAr && (
                <p className="text-sm text-slate-600 dark:text-slate-400">{stream.summaryAr}</p>
              )}
            </div>
          )}

          {isDone && !success && (
            <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
              <span>❌</span>
              <span className="text-sm">{stream.error || stream.summaryAr || 'فشل التسجيل'}</span>
            </div>
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
