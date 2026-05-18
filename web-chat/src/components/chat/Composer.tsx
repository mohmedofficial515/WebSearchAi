import { useCallback, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { SkillBadge } from './SkillBadge';
import { AttachmentPreview, type AttachmentEntry } from './AttachmentPreview';
import { ArchiveSuggestionBanner } from './ArchiveSuggestionBanner';
import { useIntent } from '@/hooks/useIntent';
import { useArchiveSuggestion } from '@/hooks/useArchiveSuggestion';
import { parseSlashCommand, getSuggestedCommands } from '@/lib/slash-commands';
import { apiUpload, type UploadResponse } from '@/lib/api';

interface ComposerProps {
  onSubmit: (text: string, skillOverride: string | null, attachments: AttachmentEntry[]) => void;
  disabled?: boolean;
}

let attachCounter = 0;
function newAttachId() { return `att-${++attachCounter}`; }

export function Composer({ onSubmit, disabled = false }: ComposerProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [skillOverride, setSkillOverride] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<AttachmentEntry[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [archiveDismissed, setArchiveDismissed] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const intentResult = useIntent(text);
  const archiveSuggestion = useArchiveSuggestion(text);
  const slashSkill = parseSlashCommand(text);
  const suggestedCommands = getSuggestedCommands(text);

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

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
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

      <div className="p-4">
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
        <div className="flex items-end gap-2">
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
}
