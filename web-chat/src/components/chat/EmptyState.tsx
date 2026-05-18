import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';

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

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.15 } },
};

const chipItem = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.25, 0.1, 0.25, 1] as const } },
};

export function EmptyState({ onChip }: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <motion.div
      className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
    >
      <motion.div
        className="text-4xl mb-4"
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease: 'backOut' }}
      >
        👋
      </motion.div>
      <h2 className="text-xl font-medium text-slate-800 dark:text-slate-200 mb-6">
        {t('empty.greeting')}
      </h2>

      <motion.div
        className="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-xl"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {CHIPS.map((chip) => (
          <motion.button
            key={chip.key}
            variants={chipItem}
            onClick={() => onChip(chip.prompt)}
            className="
              px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700
              text-sm text-slate-700 dark:text-slate-300 text-start
              hover:border-indigo-300 hover:bg-indigo-50 dark:hover:border-indigo-700 dark:hover:bg-indigo-950
              transition-colors
            "
          >
            {t(`empty.chips.${chip.key}`)}
          </motion.button>
        ))}
      </motion.div>
    </motion.div>
  );
}
