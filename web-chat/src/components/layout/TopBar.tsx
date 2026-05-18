import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useSettingsStore } from '@/stores/settingsStore';

interface TopBarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function TopBar({ sidebarOpen, onToggleSidebar }: TopBarProps) {
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme, locale, setLocale } = useSettingsStore();

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

      <div className="flex-1" />

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
