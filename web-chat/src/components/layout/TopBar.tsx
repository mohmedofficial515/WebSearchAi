import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useSettingsStore } from '@/stores/settingsStore';
import { apiFetch } from '@/lib/api';

interface TopBarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  liveActive?: boolean;
  onShowLive?: () => void;
}

interface ActiveProviderInfo {
  active: string;
  providers: Array<{ name: string; label: string; current_model?: string; is_configured: boolean }>;
}

export function TopBar({ sidebarOpen, onToggleSidebar, liveActive, onShowLive }: TopBarProps) {
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme, locale, setLocale } = useSettingsStore();
  const [activeBadge, setActiveBadge] = useState<{ label: string; model: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<ActiveProviderInfo>('/api/providers')
      .then((data) => {
        if (cancelled) return;
        const active = data.providers.find((p) => p.name === data.active && p.is_configured)
          ?? data.providers.find((p) => p.is_configured);
        if (active) {
          setActiveBadge({
            label: active.label,
            model: (active.current_model ?? '').split('/').pop() ?? '',
          });
        }
      })
      .catch(() => {/* leave the badge hidden if the call fails */});
    return () => { cancelled = true; };
  }, []);

  const toggleLocale = () => {
    const next = locale === 'ar' ? 'en' : 'ar';
    setLocale(next);
    void i18n.changeLanguage(next);
    document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = next;
  };

  const toggleDark = () => {
    toggleTheme();
    document.documentElement.classList.toggle('dark', theme === 'light');
  };

  return (
    <header className="flex items-center gap-3 px-4 py-2 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-950 h-12 flex-shrink-0">
      {/* Sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        aria-label="تبديل القائمة"
        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-600 dark:text-slate-400"
      >
        {sidebarOpen ? '◀' : '▶'}
      </button>

      {/* Brand */}
      <span className="font-medium text-slate-900 dark:text-slate-100 text-sm">
        WebSearchAi
      </span>

      {/* Active model badge — answers "which model is being used right now?" */}
      {activeBadge && (
        <Link
          to="/settings"
          title={`${activeBadge.label} · ${activeBadge.model || '—'}`}
          className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium
            bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300
            border border-indigo-100 dark:border-indigo-900 hover:bg-indigo-100 dark:hover:bg-indigo-950/60
            transition-colors"
        >
          <span className="opacity-70">{activeBadge.label}</span>
          {activeBadge.model && <><span className="opacity-50">·</span><span>{activeBadge.model}</span></>}
        </Link>
      )}

      <div className="flex-1" />

      {/* Mobile live indicator (< lg) */}
      {liveActive && onShowLive && (
        <button
          onClick={onShowLive}
          aria-label="عرض التنفيذ المباشر"
          className="lg:hidden flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 text-xs font-medium animate-pulse"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          مباشر
        </button>
      )}

      {/* Locale toggle */}
      <button
        onClick={toggleLocale}
        aria-label={t('topbar.langAr')}
        className="px-2 py-1 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700
          text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
      >
        {locale === 'ar' ? 'EN' : 'ع'}
      </button>

      {/* Theme toggle */}
      <button
        onClick={toggleDark}
        aria-label={t(theme === 'light' ? 'topbar.darkMode' : 'topbar.lightMode')}
        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-600 dark:text-slate-400"
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>

      {/* Settings */}
      <Link
        to="/settings"
        aria-label={t('topbar.settings')}
        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-600 dark:text-slate-400"
      >
        ⚙️
      </Link>
    </header>
  );
}
