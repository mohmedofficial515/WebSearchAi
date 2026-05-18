import { useTranslation } from 'react-i18next';

export interface AttachmentEntry {
  id: string;
  file: File;
  status: 'uploading' | 'done' | 'error';
  url?: string;
  mime?: string;
  errorMsg?: string;
}

interface AttachmentPreviewProps {
  attachments: AttachmentEntry[];
  onRemove: (id: string) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(mime: string): string {
  if (mime.startsWith('image/')) return '🖼';
  if (mime.startsWith('video/')) return '🎬';
  if (mime.startsWith('audio/')) return '🎵';
  if (mime.includes('pdf')) return '📑';
  if (mime.includes('zip') || mime.includes('tar') || mime.includes('gzip')) return '📦';
  if (mime.includes('json') || mime.includes('javascript') || mime.includes('typescript')) return '📄';
  return '📎';
}

export function AttachmentPreview({ attachments, onRemove }: AttachmentPreviewProps) {
  const { t } = useTranslation();

  if (attachments.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-4 pt-2 pb-1">
      {attachments.map((att) => {
        const mime = att.mime ?? att.file.type ?? 'application/octet-stream';
        const icon = fileIcon(mime);
        return (
          <div
            key={att.id}
            className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs max-w-[200px] ${
              att.status === 'error'
                ? 'border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-900/20'
                : att.status === 'uploading'
                ? 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 animate-pulse'
                : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900'
            }`}
          >
            <span className="text-base leading-none flex-shrink-0">{icon}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-slate-700 dark:text-slate-300">
                {att.file.name}
              </p>
              <p className="text-slate-400">
                {att.status === 'uploading'
                  ? t('attachment.uploading')
                  : att.status === 'error'
                  ? t('attachment.uploadError')
                  : formatBytes(att.file.size)}
              </p>
            </div>
            <button
              onClick={() => onRemove(att.id)}
              aria-label={t('attachment.remove')}
              className="flex-shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
