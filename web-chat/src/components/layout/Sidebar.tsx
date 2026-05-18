import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { TaskRecord } from '@/stores/tasksStore';

interface SidebarProps {
  tasks: TaskRecord[];
  activeTaskId: string | null;
  onNewChat: () => void;
  onSelectTask: (taskId: string) => void;
}

const STATUS_DOT: Record<TaskRecord['status'], string> = {
  running:   'bg-amber-400',
  succeeded: 'bg-emerald-400',
  failed:    'bg-rose-400',
  cancelled: 'bg-slate-400',
};

export function Sidebar({ tasks, activeTaskId, onNewChat, onSelectTask }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside className="flex flex-col h-full bg-slate-50 dark:bg-slate-900 border-e border-slate-100 dark:border-slate-800 p-3 gap-2">
      {/* New chat button */}
      <button
        onClick={onNewChat}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium
          bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
      >
        <span className="text-base">✏️</span>
        {t('sidebar.newChat')}
      </button>

      {/* Task history */}
      <div className="flex-1 overflow-y-auto mt-2 space-y-1">
        <p className="px-2 text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">
          {t('sidebar.history')}
        </p>
        {tasks.length === 0 && (
          <p className="px-2 text-sm text-slate-400">{t('sidebar.noTasks')}</p>
        )}
        {tasks.map((task) => (
          <button
            key={task.taskId}
            onClick={() => onSelectTask(task.taskId)}
            className={`
              w-full text-start px-3 py-2 rounded-lg text-sm transition-colors
              flex items-center gap-2 group
              ${activeTaskId === task.taskId
                ? 'bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
                : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
              }
            `}
          >
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[task.status]}`} />
            <span className="truncate">{task.goal}</span>
          </button>
        ))}
      </div>

      {/* Settings link */}
      <Link
        to="/settings"
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 dark:text-slate-400
          hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
      >
        <span>⚙️</span>
        {t('sidebar.settings')}
      </Link>
    </aside>
  );
}
