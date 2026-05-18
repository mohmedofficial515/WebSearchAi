import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { RightDrawer } from './RightDrawer';
import type { TaskStreamState } from '@/hooks/useTaskStream';
import type { TaskRecord } from '@/stores/tasksStore';

interface AppShellProps {
  tasks: TaskRecord[];
  activeTaskId: string | null;
  taskStream: TaskStreamState;
  onNewChat: () => void;
  onSelectTask: (taskId: string) => void;
  children: React.ReactNode;
}

export function AppShell({
  tasks,
  activeTaskId,
  taskStream,
  onNewChat,
  onSelectTask,
  children,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const drawerOpen =
    taskStream.status === 'connecting' ||
    taskStream.status === 'running' ||
    !!(taskStream.screenshot);

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-slate-950">
      {/* Sidebar */}
      <div
        className={`
          flex-shrink-0 transition-all duration-200
          ${sidebarOpen ? 'w-60' : 'w-0 overflow-hidden'}
          lg:block
        `}
      >
        <Sidebar
          tasks={tasks}
          activeTaskId={activeTaskId}
          onNewChat={onNewChat}
          onSelectTask={onSelectTask}
        />
      </div>

      {/* Main column */}
      <div className="flex flex-1 flex-col min-w-0">
        <TopBar
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* Right drawer — live execution panel */}
      {drawerOpen && (
        <div className="flex-shrink-0 w-[360px] hidden lg:block border-s border-slate-100 dark:border-slate-800">
          <RightDrawer taskStream={taskStream} />
        </div>
      )}
    </div>
  );
}
