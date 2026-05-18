import { useState, useRef, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { SkillBadge } from './SkillBadge';
import { useIntent } from '@/hooks/useIntent';
import { parseSlashCommand, getSuggestedCommands } from '@/lib/slash-commands';

interface ComposerProps {
  onSubmit: (text: string, skillOverride: string | null) => void;
  disabled?: boolean;
}

export function Composer({ onSubmit, disabled = false }: ComposerProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [skillOverride, setSkillOverride] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const intentResult = useIntent(text);
  const slashSkill = parseSlashCommand(text);
  const suggestedCommands = getSuggestedCommands(text);

  const detectedSkill = skillOverride ?? slashSkill ?? intentResult?.intent ?? null;
  const confidence = skillOverride ? 1 : slashSkill ? 1 : intentResult?.confidence;

  const canSend = text.trim().length > 0 && !disabled;

  const handleSubmit = () => {
    if (!canSend) return;
    onSubmit(text.trim(), skillOverride ?? slashSkill);
    setText('');
    setSkillOverride(null);
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // reset height then grow
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  };

  return (
    <div className="border-t border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-950 p-4">
      {/* Slash command suggestions */}
      {suggestedCommands.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {suggestedCommands.map((cmd) => (
            <button
              key={cmd.command}
              onClick={() => setText(cmd.command + ' ')}
              className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800
                text-slate-600 dark:text-slate-400 hover:bg-indigo-50 hover:text-indigo-700
                dark:hover:bg-indigo-950 dark:hover:text-indigo-300 transition-colors"
            >
              <span className="font-mono">{cmd.command}</span>
              <span className="ms-1 opacity-60">{cmd.labelAr}</span>
            </button>
          ))}
        </div>
      )}

      {/* Skill badge row */}
      {(detectedSkill || intentResult) && (
        <div className="mb-2 flex items-center gap-2">
          <SkillBadge
            skill={detectedSkill}
            confidence={confidence}
            onOverride={(id) => setSkillOverride(id)}
          />
          {skillOverride && (
            <button
              onClick={() => setSkillOverride(null)}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              ✕ {t('skill.auto')}
            </button>
          )}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-3">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={t('composer.placeholder')}
          rows={1}
          className="
            flex-1 resize-none rounded-xl border border-slate-200 dark:border-slate-700
            bg-slate-50 dark:bg-slate-900 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200
            placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300
            dark:focus:ring-indigo-700 transition-all
            disabled:opacity-50 disabled:cursor-not-allowed
            min-h-[42px] max-h-[200px] overflow-y-auto
          "
          style={{ direction: 'auto' }}
        />

        <button
          onClick={handleSubmit}
          disabled={!canSend}
          aria-label={t('composer.send')}
          className="
            flex-shrink-0 w-10 h-10 rounded-xl bg-indigo-600 text-white
            flex items-center justify-center
            hover:bg-indigo-700 transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed
          "
        >
          ↑
        </button>
      </div>
    </div>
  );
}
