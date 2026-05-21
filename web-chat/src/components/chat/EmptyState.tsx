import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';

interface EmptyStateProps {
  onChip: (text: string) => void;
}

const CHIPS: { key: string; icon: string; prompt: string; color: string }[] = [
  {
    key: 'search',
    icon: '🔍',
    prompt: 'ابحث عن أفضل مكتبات React في 2025',
    color: 'hover:border-blue-300 hover:bg-blue-50 dark:hover:border-blue-700 dark:hover:bg-blue-950',
  },
  {
    key: 'html',
    icon: '🌐',
    prompt: 'أنشئ صفحة هبوط HTML لتطبيق موبايل',
    color: 'hover:border-orange-300 hover:bg-orange-50 dark:hover:border-orange-700 dark:hover:bg-orange-950',
  },
  {
    key: 'explore',
    icon: '🎨',
    prompt: 'حلّل موقع https://tailwindcss.com وقدّم تقريراً',
    color: 'hover:border-purple-300 hover:bg-purple-50 dark:hover:border-purple-700 dark:hover:bg-purple-950',
  },
  {
    key: 'md',
    icon: '📄',
    prompt: 'اكتب تقرير ماركداون عن مستقبل الذكاء الاصطناعي',
    color: 'hover:border-green-300 hover:bg-green-50 dark:hover:border-green-700 dark:hover:bg-green-950',
  },
  {
    key: 'compare',
    icon: '📊',
    prompt: 'قارن مواقع منافسة في مجال التجارة الإلكترونية',
    color: 'hover:border-indigo-300 hover:bg-indigo-50 dark:hover:border-indigo-700 dark:hover:bg-indigo-950',
  },
  {
    key: 'design',
    icon: '✨',
    prompt: 'صمّم لي صفحة ERP احترافية بالعربية',
    color: 'hover:border-violet-300 hover:bg-violet-50 dark:hover:border-violet-700 dark:hover:bg-violet-950',
  },
];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.15 } },
};

const chipItem = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.25, 0.1, 0.25, 1] as const } },
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
        className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-2xl mb-5 shadow-lg shadow-indigo-200 dark:shadow-indigo-900/40"
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease: 'backOut' }}
      >
        🤖
      </motion.div>

      <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 mb-1">
        {t('empty.greeting')}
      </h2>
      <p className="text-sm text-slate-400 dark:text-slate-500 mb-7">
        اختر مهمة أو اكتب هدفك مباشرة في الحقل أدناه
      </p>

      <motion.div
        className="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-xl"
        variants={container}
        initial="hidden"
        animate="show"
      >
        {CHIPS.map((chip) => {
          const labelKey = chip.key === 'design' ? null : `empty.chips.${chip.key}`;
          const label = labelKey ? t(labelKey) : 'وكيل التصميم التفاعلي';
          return (
            <motion.button
              key={chip.key}
              variants={chipItem}
              onClick={() => onChip(chip.prompt)}
              className={`
                flex items-center gap-3 px-4 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700
                text-sm text-slate-700 dark:text-slate-300 text-start bg-white dark:bg-slate-900
                ${chip.color} transition-all duration-150 shadow-sm hover:shadow-md group
              `}
            >
              <span className="text-xl leading-none flex-shrink-0 group-hover:scale-110 transition-transform">{chip.icon}</span>
              <span className="font-medium leading-snug">{label}</span>
            </motion.button>
          );
        })}
      </motion.div>

      <p className="text-[11px] text-slate-300 dark:text-slate-600 mt-7">
        اكتب <kbd className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono text-slate-500 dark:text-slate-400">/</kbd> لرؤية جميع الأوامر المتاحة
      </p>
    </motion.div>
  );
}
