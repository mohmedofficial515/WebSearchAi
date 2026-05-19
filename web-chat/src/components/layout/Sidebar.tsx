import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { TaskRecord } from '@/stores/tasksStore';
import type { Conversation } from '@/stores/conversationsStore';
import { formatTokens } from '@/lib/tokens';

interface SidebarProps {
  tasks: TaskRecord[];
  activeTaskId: string | null;
  onNewChat: () => void;
  onSelectTask: (taskId: string) => void;
  conversations?: Conversation[];
  activeConversationId?: string | null;
  onSelectConversation?: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  totalTokens?: number;
}

export function Sidebar({
  activeTaskId,
  onNewChat,
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  totalTokens,
}: SidebarProps) {
  const { t } = useTranslation();
  const hasConversations = conversations && conversations.length > 0;

  return (
    <aside className="flex flex-col h-full bg-slate-50 dark:bg-slate-900 border-e border-slate-100 dark:border-slate-800 p-3 gap-2 w-full">
      {/* New chat button */}
      <button
        onClick={onNewChat}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium
          bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
      >
        <span className="text-base">✏️</span>
        {t('sidebar.newChat')}
      </button>

      {/* Total token counter for active conversation */}
      {totalTokens !== undefined && totalTokens > 0 && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400">
          <span>🔢 {t('sidebar.tokens')}</span>
          <span className="font-mono font-medium text-indigo-600 dark:text-indigo-400">
            {formatTokens(totalTokens)}
          </span>
        </div>
      )}

      {/* Conversation history */}
      <div className="flex-1 overflow-y-auto mt-1 space-y-0.5">
        <p className="px-2 text-[11px] font-medium text-slate-400 uppercase tracking-wide mb-1">
          {t('sidebar.history')}
        </p>

        {!hasConversations && (
          <p className="px-2 text-sm text-slate-400">{t('sidebar.noTasks')}</p>
        )}

        {conversations?.map((conv) => {
          const isActive = conv.id === activeConversationId;
          return (
            <div
              key={conv.id}
              className={`
                group flex items-center gap-1 rounded-lg transition-colors
                ${isActive
                  ? 'bg-indigo-50 dark:bg-indigo-950'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                }
              `}
            >
              <button
                onClick={() => onSelectConversation?.(conv.id)}
                className={`
                  flex-1 text-start px-3 py-2 text-sm min-w-0
                  ${isActive
                    ? 'text-indigo-700 dark:text-indigo-300'
                    : 'text-slate-700 dark:text-slate-300'
                  }
                `}
              >
                <p className="truncate leading-snug">{conv.title}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-slate-400 font-mono">
                    {formatTokens(conv.totalTokens)} tok
                  </span>
                  <span className="text-[10px] text-slate-300 dark:text-slate-600">
                    {conv.messages.length} رسالة
                  </span>
                </div>
              </button>
              {onDeleteConversation && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm('حذف هذه المحادثة؟')) onDeleteConversation(conv.id);
                  }}
                  aria-label="حذف"
                  className="opacity-0 group-hover:opacity-100 me-1 flex-shrink-0 w-6 h-6 rounded flex items-center justify-center text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-xs transition-all"
                >
                  🗑
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Active task indicator */}
      {activeTaskId && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/50">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0" />
          <span className="text-xs text-amber-700 dark:text-amber-400 truncate">
            {t('task.running')}
          </span>
        </div>
      )}

      {/* Navigation links */}
      <div className="space-y-0.5">
        <Link
          to="/artifacts"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 dark:text-slate-400
            hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <span>📁</span>
          <span>{t('artifacts.title')}</span>
        </Link>
        <Link
          to="/settings"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 dark:text-slate-400
            hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <span>⚙️</span>
          {t('sidebar.settings')}
        </Link>
      </div>
    </aside>
  );
}
