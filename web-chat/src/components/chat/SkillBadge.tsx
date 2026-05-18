import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { SKILLS, getSkill } from '@/lib/skills';

interface SkillBadgeProps {
  skill: string | null;
  confidence?: number;
  onOverride: (skillId: string) => void;
}

export function SkillBadge({ skill, confidence, onOverride }: SkillBadgeProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const meta = skill ? getSkill(skill) : null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        title={t('skill.override')}
        className={`
          inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
          transition-colors border
          ${meta
            ? `${meta.color} border-transparent`
            : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
          }
        `}
      >
        {meta ? (
          <>
            <span>{meta.icon}</span>
            <span>{meta.labelAr}</span>
            {confidence !== undefined && confidence < 0.8 && (
              <span className="opacity-50">?</span>
            )}
          </>
        ) : (
          <span>{t('skill.detecting')}</span>
        )}
        <span className="opacity-50 text-xs">▾</span>
      </button>

      {open && (
        <div className="absolute top-full mt-1 end-0 z-50 w-48 rounded-xl border border-slate-100 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg py-1 max-h-64 overflow-y-auto">
          <p className="px-3 py-1 text-xs text-slate-400">{t('skill.override')}</p>
          {SKILLS.map((s) => (
            <button
              key={s.id}
              onClick={() => { onOverride(s.id); setOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <span>{s.icon}</span>
              <span>{s.labelAr}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
