import { useTranslation } from 'react-i18next';
import type { TimelineStep } from '@/hooks/useTaskStream';
import type { PlanStep } from '@/lib/events';
import { ActionIcon } from './ActionIcon';

interface TimelineStripProps {
  steps: TimelineStep[];
  plan: PlanStep[] | null;
}

export function TimelineStrip({ steps, plan }: TimelineStripProps) {
  const { t } = useTranslation();

  if (steps.length === 0 && !plan) {
    return (
      <p className="text-sm text-slate-400">{t('timeline.noSteps')}</p>
    );
  }

  return (
    <div className="space-y-1">
      {plan && (
        <div className="mb-2 p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
          <p className="text-xs font-medium text-slate-500 mb-1">{t('timeline.plan')}</p>
          <ol className="space-y-0.5">
            {plan.map((s, i) => (
              <li key={s.id} className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
                <span className="text-slate-400">{i + 1}.</span>
                <span className="font-mono text-slate-500">{s.skill}</span>
                <span className="truncate">{s.goal}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {steps.map((step, i) => (
        <div
          key={i}
          className={`
            flex items-start gap-2 p-2 rounded-lg text-xs
            ${step.ok === false ? 'bg-rose-50 dark:bg-rose-950/30' : 'bg-white dark:bg-slate-800'}
          `}
        >
          <ActionIcon actionType={step.actionType} className="mt-0.5 flex-shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-slate-700 dark:text-slate-300 font-medium truncate">
              {step.actionLabel}
            </p>
            {step.note && (
              <p className="text-slate-400 dark:text-slate-500 truncate">{step.note}</p>
            )}
          </div>
          {step.ok !== undefined && (
            <span className="flex-shrink-0">{step.ok ? '✅' : '❌'}</span>
          )}
        </div>
      ))}
    </div>
  );
}
