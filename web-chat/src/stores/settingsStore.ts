import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface SettingsState {
  locale: 'ar' | 'en';
  theme: 'light' | 'dark';
  headless: boolean;
  useVision: boolean;
  setLocale: (locale: 'ar' | 'en') => void;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;
  setHeadless: (v: boolean) => void;
  setUseVision: (v: boolean) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      locale: 'ar',
      theme: 'light',
      headless: true,
      useVision: false,
      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set({ theme: get().theme === 'light' ? 'dark' : 'light' }),
      setHeadless: (headless) => set({ headless }),
      setUseVision: (useVision) => set({ useVision }),
    }),
    { name: 'websearchai-settings' },
  ),
);
