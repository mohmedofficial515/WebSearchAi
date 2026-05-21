import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { SkillBadge } from './SkillBadge';
import { SlashCommandDropdown } from './SlashCommandDropdown';
import { AttachmentPreview, type AttachmentEntry } from './AttachmentPreview';
import { ArchiveSuggestionBanner } from './ArchiveSuggestionBanner';
import { useIntent } from '@/hooks/useIntent';
import { useArchiveSuggestion } from '@/hooks/useArchiveSuggestion';
import { parseSlashCommand, getSuggestedCommands, type SlashCommand } from '@/lib/slash-commands';
import { apiUpload, type UploadResponse } from '@/lib/api';
import { estimateTokens, formatTokens } from '@/lib/tokens';

interface ComposerProps {
  onSubmit: (text: string, skillOverride: string | null, attachments: AttachmentEntry[]) => void;
  disabled?: boolean;
  totalTokens?: number;
}

export interface ComposerHandle {
  focus: () => void;
}

let attachCounter = 0;
function newAttachId() { return `att-${++attachCounter}`; }

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer(
  { onSubmit, disabled = false, totalTokens },
  ref,
) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [skillOverride, setSkillOverride] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AttachmentEntry[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [archiveDismissed, setArchiveDismissed] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => { textareaRef.current?.focus(); },
  }));

  const intentResult = useIntent(text);
  const archiveSuggestion = useArchiveSuggestion(text);
  const slashSkill = parseSlashCommand(text);
  const suggestedCommands = useMemo(() => getSuggestedCommands(text), [text]);

  // Slash dropdown is open when input starts with `/` and the user is still
  // editing the first token (i.e. no space yet — once they typed a space we
  // treat the command as locked-in and the dropdown closes).
  const showSlashDropdown = text.startsWith('/') && !text.includes(' ');
  const [slashIndex, setSlashIndex] = useState(0);

  // Reset selection whenever the suggestion list shrinks/changes shape
  useEffect(() => {
    if (slashIndex >= suggestedCommands.length) setSlashIndex(0);
  }, [suggestedCommands.length, slashIndex]);

  const detectedSkill = skillOverride ?? slashSkill ?? intentResult?.intent ?? null;
  const confidence = skillOverride ? 1 : slashSkill ? 1 : intentResult?.confidence;

  const canSend = text.trim().length > 0 && !disabled;

  // ── Upload a single file ────────────────────────────────────────────────
  const uploadFile = useCallback(async (file: File): Promise<void> => {
    const id = newAttachId();
    const entry: AttachmentEntry = { id, file, status: 'uploading' };
    setAttachments((prev) => [...prev, entry]);

    const form = new FormData();
    form.append('file', file);
    try {
      const res = await apiUpload<UploadResponse>('/api/uploads', form);
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, status: 'done', url: res.url, mime: res.mime } : a,
        ),
      );
    } catch {
      setAttachments((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: 'error' } : a)),
      );
    }
  }, []);

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      Array.from(files).forEach((f) => uploadFile(f));
    },
    [uploadFile],
  );

  // ── Submit ──────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(() => {
    if (!canSend) return;
    onSubmit(text.trim(), skillOverride ?? slashSkill, attachments);
    setText('');
    setSkillOverride(null);
    setAttachments([]);
    setArchiveDismissed(false);
    textareaRef.current?.focus();
  }, [canSend, text, skillOverride, slashSkill, attachments, onSubmit]);

  const pickSlashCommand = useCallback((cmd: SlashCommand) => {
    setText(cmd.command + ' ');
    // Refocus and place caret at end
    requestAnimationFrame(() => {
      const ta = textareaRef.current;
      if (!ta) return;
      ta.focus();
      const len = ta.value.length;
      ta.setSelectionRange(len, len);
    });
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashDropdown && suggestedCommands.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlashIndex((i) => (i + 1) % suggestedCommands.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlashIndex((i) => (i - 1 + suggestedCommands.length) % suggestedCommands.length);
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        const cmd = suggestedCommands[slashIndex];
        if (cmd) pickSlashCommand(cmd);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setText('');
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    setArchiveDismissed(false);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  };

  // ── Drag and drop ───────────────────────────────────────────────────────
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  // ── Paste ───────────────────────────────────────────────────────────────
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (e.clipboardData.files.length > 0) {
      e.preventDefault();
      handleFiles(e.clipboardData.files);
    }
  };

  // ── Archive suggestion ──────────────────────────────────────────────────
  const showSuggestion = archiveSuggestion !== null && !archiveDismissed;

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`border-t border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-950 transition-colors ${
        isDragOver ? 'bg-indigo-50 dark:bg-indigo-950/30 border-indigo-300 dark:border-indigo-700' : ''
      }`}
    >
      {/* Drag overlay label */}
      {isDragOver && (
        <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <span className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium shadow-lg">
            {t('attachment.dragDrop')}
          </span>
        </div>
      )}

      {/* Archive suggestion banner */}
      {showSuggestion && archiveSuggestion && (
        <ArchiveSuggestionBanner
          suggestion={archiveSuggestion}
          onUse={() => {
            setText(archiveSuggestion.goal);
            setArchiveDismissed(true);
            textareaRef.current?.focus();
          }}
          onDismiss={() => setArchiveDismissed(true)}
        />
      )}

      {/* Attachment previews */}
      <AttachmentPreview
        attachments={attachments}
        onRemove={(id) => setAttachments((prev) => prev.filter((a) => a.id !== id))}
      />

      <div className="p-4 relative">
        {/* Slash command dropdown (Cmd-K style picker) */}
        {showSlashDropdown && (
          <SlashCommandDropdown
            commands={suggestedCommands}
            activeIndex={slashIndex}
            onSelect={pickSlashCommand}
            onHover={setSlashIndex}
          />
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
                aria-label={t('skill.clearOverride')}
                className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                ✕ {t('skill.auto')}
              </button>
            )}
          </div>
        )}

        {/* Token counter row */}
        {(text.length > 0 || (totalTokens !== undefined && totalTokens > 0)) && (
          <div className="flex items-center justify-between mb-1.5 px-1 text-[11px] text-slate-400 font-mono">
            {text.length > 0 ? (
              <span>+{formatTokens(estimateTokens(text))} tok</span>
            ) : (
              <span />
            )}
            {totalTokens !== undefined && totalTokens > 0 && (
              <span className="text-slate-300 dark:text-slate-600">
                {t('composer.totalTokens')}: {formatTokens(totalTokens)}
              </span>
            )}
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2">
          {/* Slash command picker button */}
          <button
            type="button"
            onClick={() => {
              setText('/');
              requestAnimationFrame(() => {
                const ta = textareaRef.current;
                if (!ta) return;
                ta.focus();
                ta.setSelectionRange(1, 1);
              });
            }}
            disabled={disabled}
            aria-label={t('composer.slash', 'الأوامر السريعة')}
            title={t('composer.slash', 'الأوامر السريعة')}
            className="flex-shrink-0 w-9 h-9 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 flex items-center justify-center hover:bg-indigo-100 hover:text-indigo-600 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm font-mono font-semibold"
          >
            /
          </button>

          {/* Attach button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label={t('composer.attach')}
            className="flex-shrink-0 w-9 h-9 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-base"
          >
            📎
          </button>

          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
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
            dir="auto"
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

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => { if (e.target.files) { handleFiles(e.target.files); e.target.value = ''; } }}
      />
    </div>
  );
});
