import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
  const [drawerDismissed, setDrawerDismissed] = useState(false);

  const drawerShouldShow =
    taskStream.status === 'connecting' ||
    taskStream.status === 'running' ||
    !!(taskStream.screenshot);

  const drawerOpen = drawerShouldShow && !drawerDismissed;

  // Reset dismissed state whenever a new live stream starts
  const prevShouldShow = useRef(drawerShouldShow);
  useEffect(() => {
    if (!prevShouldShow.current && drawerShouldShow) {
      setDrawerDismissed(false);
    }
    prevShouldShow.current = drawerShouldShow;
  }, [drawerShouldShow]);

  // Escape = close right drawer
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && drawerOpen) {
        setDrawerDismissed(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [drawerOpen]);

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
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            key="right-drawer"
            className="flex-shrink-0 w-[360px] hidden lg:flex flex-col border-s border-slate-100 dark:border-slate-800 relative"
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <button
              onClick={() => setDrawerDismissed(true)}
              aria-label="إغلاق اللوحة"
              className="absolute end-2 top-2 z-10 w-6 h-6 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs transition-colors"
            >
              ✕
            </button>
            <RightDrawer taskStream={taskStream} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
