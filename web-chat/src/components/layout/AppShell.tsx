import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { RightDrawer } from './RightDrawer';
import type { TaskStreamState } from '@/hooks/useTaskStream';
import type { TaskRecord } from '@/stores/tasksStore';
import type { Conversation } from '@/stores/conversationsStore';

interface AppShellProps {
  tasks: TaskRecord[];
  activeTaskId: string | null;
  taskStream: TaskStreamState;
  onNewChat: () => void;
  onSelectTask: (taskId: string) => void;
  // Conversation-aware props (optional for non-chat pages)
  conversations?: Conversation[];
  activeConversationId?: string | null;
  onSelectConversation?: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  totalTokens?: number;
  children: React.ReactNode;
}

export function AppShell({
  tasks,
  activeTaskId,
  taskStream,
  onNewChat,
  onSelectTask,
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  totalTokens,
  children,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [drawerDismissed, setDrawerDismissed] = useState(false);
  const [mobileLiveOpen, setMobileLiveOpen] = useState(false);

  const drawerShouldShow =
    taskStream.status === 'connecting' ||
    taskStream.status === 'running' ||
    !!(taskStream.screenshot);

  const drawerOpen = drawerShouldShow && !drawerDismissed;

  const prevShouldShow = useRef(drawerShouldShow);
  useEffect(() => {
    if (!prevShouldShow.current && drawerShouldShow) {
      setDrawerDismissed(false);
    }
    prevShouldShow.current = drawerShouldShow;
  }, [drawerShouldShow]);

  useEffect(() => {
    if (!drawerShouldShow) setMobileLiveOpen(false);
  }, [drawerShouldShow]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (mobileLiveOpen) { setMobileLiveOpen(false); return; }
        if (drawerOpen) { setDrawerDismissed(true); return; }
        if (sidebarOpen) setSidebarOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [drawerOpen, mobileLiveOpen, sidebarOpen]);

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-slate-950">

      {/* ── Desktop sidebar (lg+) ── */}
      <div
        className={`
          hidden lg:flex flex-shrink-0 transition-all duration-200
          ${sidebarOpen ? 'w-64' : 'w-0 overflow-hidden'}
        `}
      >
        <Sidebar
          tasks={tasks}
          activeTaskId={activeTaskId}
          onNewChat={onNewChat}
          onSelectTask={onSelectTask}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={onSelectConversation}
          onDeleteConversation={onDeleteConversation}
          totalTokens={totalTokens}
        />
      </div>

      {/* ── Mobile sidebar overlay (< lg) ── */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="sidebar-backdrop"
              className="fixed inset-0 z-30 bg-black/40 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => setSidebarOpen(false)}
            />
            <motion.div
              key="sidebar-panel"
              className="fixed inset-y-0 start-0 z-40 w-64 lg:hidden"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <Sidebar
                tasks={tasks}
                activeTaskId={activeTaskId}
                onNewChat={() => { onNewChat(); setSidebarOpen(false); }}
                onSelectTask={(id) => { onSelectTask(id); setSidebarOpen(false); }}
                conversations={conversations}
                activeConversationId={activeConversationId}
                onSelectConversation={(id) => { onSelectConversation?.(id); setSidebarOpen(false); }}
                onDeleteConversation={onDeleteConversation}
                totalTokens={totalTokens}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── Main column ── */}
      <div className="flex flex-1 flex-col min-w-0">
        <TopBar
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          liveActive={drawerShouldShow}
          onShowLive={() => setMobileLiveOpen(true)}
        />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* ── Desktop right drawer (lg+) ── */}
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

      {/* ── Mobile bottom live sheet (< lg) ── */}
      <AnimatePresence>
        {mobileLiveOpen && (
          <>
            <motion.div
              key="live-backdrop"
              className="fixed inset-0 z-40 bg-black/40 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => setMobileLiveOpen(false)}
            />
            <motion.div
              key="live-sheet"
              className="fixed inset-x-0 bottom-0 z-50 h-[55vh] lg:hidden rounded-t-2xl overflow-hidden shadow-xl"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              <div className="bg-slate-50 dark:bg-slate-900 flex justify-center pt-3 pb-1">
                <div className="w-10 h-1 rounded-full bg-slate-300 dark:bg-slate-600" />
              </div>
              <div className="h-full">
                <RightDrawer taskStream={taskStream} />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
