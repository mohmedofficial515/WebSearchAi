import { useTranslation } from 'react-i18next';
import type { TaskStreamState } from '@/hooks/useTaskStream';
import { LiveScreenshot } from '@/components/live/LiveScreenshot';
import { TimelineStrip } from '@/components/live/TimelineStrip';

interface RightDrawerProps {
  taskStream: TaskStreamState;
}

export function RightDrawer({ taskStream }: RightDrawerProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-900 overflow-hidden">
      {/* Screenshot */}
      <div className="p-3 border-b border-slate-100 dark:border-slate-800">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
          {t('drawer.screenshot')}
        </p>
        <LiveScreenshot screenshot={taskStream.screenshot} status={taskStream.status} />
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto p-3">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
          {t('drawer.timeline')}
        </p>
        <TimelineStrip steps={taskStream.steps} plan={taskStream.plan} />
      </div>
    </div>
  );
}
