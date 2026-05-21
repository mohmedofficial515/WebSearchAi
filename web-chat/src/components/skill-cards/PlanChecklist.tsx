import type { PlanStep } from '@/lib/events';

interface PlanChecklistProps {
  steps: PlanStep[];
  /** How many steps have been completed so far (inferred from decision events) */
  completedCount: number;
  /** Whether the task is still running */
  running: boolean;
}

const stepStateClass = (idx: number, completedCount: number, running: boolean, total: number) => {
  if (idx < completedCount) return 'done';
  if (idx === completedCount && running && idx < total) return 'active';
  return 'pending';
};

export function PlanChecklist({ steps, completedCount, running }: PlanChecklistProps) {
  if (!steps.length) return null;

  return (
    <div className="mb-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-2">
        خطة التنفيذ
      </p>
      <div className="space-y-1.5">
        {steps.map((step, idx) => {
          const state = stepStateClass(idx, completedCount, running, steps.length);
          return (
            <div key={step.id} className="flex items-center gap-2.5">
              {/* State indicator */}
              <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
                {state === 'done' && (
                  <span className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center text-white text-[9px]">✓</span>
                )}
                {state === 'active' && (
                  <span className="w-4 h-4 rounded-full bg-indigo-500 animate-pulse flex items-center justify-center" />
                )}
                {state === 'pending' && (
                  <span className="w-4 h-4 rounded-full border-2 border-slate-200 dark:border-slate-700" />
                )}
              </div>
              <span className={`text-xs ${
                state === 'done'   ? 'text-slate-400 dark:text-slate-500 line-through' :
                state === 'active' ? 'text-indigo-600 dark:text-indigo-400 font-medium' :
                                     'text-slate-500 dark:text-slate-400'
              }`}>
                {step.skill}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
