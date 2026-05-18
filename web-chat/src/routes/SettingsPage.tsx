import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/layout/AppShell';
import { ProvidersPanel } from '@/components/settings/ProvidersPanel';
import { AccountsLedger } from '@/components/settings/AccountsLedger';
import { ArchiveBrowser } from '@/components/settings/ArchiveBrowser';
import { useTasksStore } from '@/stores/tasksStore';
import { useTaskStream } from '@/hooks/useTaskStream';

type TabId = 'providers' | 'accounts' | 'archive';

const TABS: { id: TabId; icon: string }[] = [
  { id: 'providers', icon: '🤖' },
  { id: 'accounts', icon: '📧' },
  { id: 'archive', icon: '📦' },
];

export default function SettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { tasks, activeTaskId } = useTasksStore();
  const stream = useTaskStream(null);
  const [activeTab, setActiveTab] = useState<TabId>('providers');

  const handleReplay = (goal: string) => {
    // Navigate to chat and pre-fill goal via URL state
    navigate('/chat', { state: { prefillGoal: goal } });
  };

  return (
    <AppShell
      tasks={tasks}
      activeTaskId={activeTaskId}
      taskStream={stream}
      onNewChat={() => navigate('/chat')}
      onSelectTask={() => navigate('/chat')}
    >
      <div className="chat-column py-6">
        {/* Page title */}
        <h1 className="text-2xl font-medium text-slate-800 dark:text-slate-200 mb-6">
          {t('settings.title')}
        </h1>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 border-b border-slate-200 dark:border-slate-700">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{t(`settings.tabs.${tab.id}`)}</span>
            </button>
          ))}
        </div>

        {/* Panel content */}
        <div>
          {activeTab === 'providers' && <ProvidersPanel />}
          {activeTab === 'accounts' && <AccountsLedger />}
          {activeTab === 'archive' && <ArchiveBrowser onReplay={handleReplay} />}
        </div>
      </div>
    </AppShell>
  );
}
