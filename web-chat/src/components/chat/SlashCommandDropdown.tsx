import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { SlashCommand } from '@/lib/slash-commands';

interface SlashCommandDropdownProps {
  commands: SlashCommand[];
  activeIndex: number;
  onSelect: (cmd: SlashCommand) => void;
  onHover: (index: number) => void;
}

const CATEGORY_LABEL_AR: Record<SlashCommand['category'], string> = {
  research:  'بحث',
  web:       'مواقع',
  auth:      'حسابات',
  artifact:  'مخرجات',
  transform: 'تحويل',
  misc:      'متفرّقات',
};

const CATEGORY_LABEL_EN: Record<SlashCommand['category'], string> = {
  research:  'Research',
  web:       'Web',
  auth:      'Auth',
  artifact:  'Artifacts',
  transform: 'Transform',
  misc:      'Other',
};

export function SlashCommandDropdown({
  commands,
  activeIndex,
  onSelect,
  onHover,
}: SlashCommandDropdownProps) {
  const { i18n } = useTranslation();
  const isAr = i18n.language === 'ar' || i18n.language.startsWith('ar');
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll the active item into view when index changes
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLButtonElement>(
      `[data-slash-index="${activeIndex}"]`,
    );
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (commands.length === 0) {
    return (
      <div className="absolute bottom-full mb-2 inset-x-0 z-30 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg px-4 py-3 text-sm text-slate-500">
        {isAr ? 'لا توجد أوامر مطابقة' : 'No matching commands'}
      </div>
    );
  }

  // Build a flat list but inject category headers when category changes
  const items: Array<
    | { kind: 'header'; category: SlashCommand['category'] }
    | { kind: 'item'; cmd: SlashCommand; index: number }
  > = [];
  let lastCategory: SlashCommand['category'] | null = null;
  commands.forEach((cmd, i) => {
    if (cmd.category !== lastCategory) {
      items.push({ kind: 'header', category: cmd.category });
      lastCategory = cmd.category;
    }
    items.push({ kind: 'item', cmd, index: i });
  });

  return (
    <div
      ref={listRef}
      className="absolute bottom-full mb-2 inset-x-0 z-30
        rounded-xl border border-slate-200 dark:border-slate-700
        bg-white dark:bg-slate-900 shadow-xl
        max-h-80 overflow-y-auto py-1"
      role="listbox"
      aria-label={isAr ? 'أوامر سريعة' : 'Quick commands'}
    >
      {items.map((item, k) => {
        if (item.kind === 'header') {
          return (
            <div
              key={`h-${item.category}-${k}`}
              className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500"
            >
              {isAr ? CATEGORY_LABEL_AR[item.category] : CATEGORY_LABEL_EN[item.category]}
            </div>
          );
        }
        const { cmd, index } = item;
        const isActive = index === activeIndex;
        return (
          <button
            key={cmd.command}
            data-slash-index={index}
            role="option"
            aria-selected={isActive}
            onMouseDown={(e) => {
              // Use mousedown so the click fires before textarea blur
              e.preventDefault();
              onSelect(cmd);
            }}
            onMouseEnter={() => onHover(index)}
            className={`
              w-full flex items-start gap-3 px-3 py-2 text-start
              transition-colors
              ${isActive
                ? 'bg-indigo-50 dark:bg-indigo-950/40'
                : 'hover:bg-slate-50 dark:hover:bg-slate-800'}
            `}
          >
            <span className="text-lg leading-none mt-0.5 flex-shrink-0">{cmd.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs font-medium ${
                  isActive ? 'text-indigo-700 dark:text-indigo-300' : 'text-slate-700 dark:text-slate-200'
                }`}>
                  {cmd.command}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {isAr ? cmd.labelAr : cmd.labelEn}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">
                {isAr ? cmd.descriptionAr : cmd.descriptionEn}
              </p>
            </div>
            {isActive && (
              <span className="text-[10px] font-mono text-indigo-500 dark:text-indigo-400 mt-1 flex-shrink-0">
                ↵
              </span>
            )}
          </button>
        );
      })}
      <div className="px-3 py-2 mt-1 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-400 flex items-center gap-3">
        <span><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono">↑↓</kbd> {isAr ? 'تنقّل' : 'navigate'}</span>
        <span><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono">↵</kbd> {isAr ? 'اختيار' : 'select'}</span>
        <span><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono">esc</kbd> {isAr ? 'إغلاق' : 'close'}</span>
      </div>
    </div>
  );
}
