import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/layout/AppShell';
import { useTasksStore } from '@/stores/tasksStore';
import { useTaskStream } from '@/hooks/useTaskStream';

export default function ArtifactsPage() {
  const { t } = useTranslation();
  const { tasks, activeTaskId } = useTasksStore();
  const stream = useTaskStream(null);

  return (
    <AppShell
      tasks={tasks}
      activeTaskId={activeTaskId}
      taskStream={stream}
      onNewChat={() => {}}
      onSelectTask={() => {}}
    >
      <div className="chat-column py-10">
        <h1 className="text-2xl font-medium text-slate-800 dark:text-slate-200 mb-4">
          {t('artifacts.title')}
        </h1>
        <p className="text-slate-400">{t('artifacts.comingSoon')}</p>
      </div>
    </AppShell>
  );
}
