import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  onChip: (text: string) => void;
}

const CHIPS = [
  { key: 'search',  prompt: 'ابحث عن أفضل مكتبات React في 2025' },
  { key: 'explore', prompt: 'حلّل موقع https://tailwindcss.com وقدّم تقريراً' },
  { key: 'md',      prompt: 'اكتب تقرير ماركداون عن مستقبل الذكاء الاصطناعي' },
  { key: 'html',    prompt: 'أنشئ صفحة هبوط HTML لتطبيق موبايل' },
  { key: 'compare', prompt: 'قارن مواقع منافسة في مجال التجارة الإلكترونية' },
  { key: 'login',   prompt: 'سجّل دخولي إلى الموقع https://example.com' },
];

export function EmptyState({ onChip }: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
      <div className="text-4xl mb-4">👋</div>
      <h2 className="text-xl font-medium text-slate-800 dark:text-slate-200 mb-6">
        {t('empty.greeting')}
      </h2>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-xl">
        {CHIPS.map((chip) => (
          <button
            key={chip.key}
            onClick={() => onChip(chip.prompt)}
            className="
              px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700
              text-sm text-slate-700 dark:text-slate-300 text-start
              hover:border-indigo-300 hover:bg-indigo-50 dark:hover:border-indigo-700 dark:hover:bg-indigo-950
              transition-colors
            "
          >
            {t(`empty.chips.${chip.key}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
