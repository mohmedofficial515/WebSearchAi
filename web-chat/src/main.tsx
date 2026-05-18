import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import ar from './locales/ar.json';
import en from './locales/en.json';
import './styles/globals.css';
import App from './App.tsx';

// i18n setup
await i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ar: { translation: ar },
      en: { translation: en },
    },
    fallbackLng: 'ar',
    supportedLngs: ['ar', 'en'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

// Apply initial dir/lang
const lang = i18n.language.startsWith('en') ? 'en' : 'ar';
document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
document.documentElement.lang = lang;

// Apply saved theme
const saved = localStorage.getItem('websearchai-settings');
if (saved) {
  try {
    const parsed = JSON.parse(saved) as { state?: { theme?: string } };
    if (parsed.state?.theme === 'dark') {
      document.documentElement.classList.add('dark');
    }
  } catch {
    // ignore
  }
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
