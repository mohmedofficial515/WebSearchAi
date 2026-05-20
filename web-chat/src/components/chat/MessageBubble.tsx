import { memo } from 'react';
import { formatTokens } from '@/lib/tokens';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  text: string;
  timestamp?: number;
  tokenCount?: number;
  // When true, the bubble renders a typing-indicator instead of text.
  // Used by ChatThread to surface "the model is deciding whether to
  // search or just reply" between submit and the /api/chat response.
  thinking?: boolean;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
}

export const MessageBubble = memo(function MessageBubble({
  role,
  text,
  timestamp,
  tokenCount,
  thinking = false,
}: MessageBubbleProps) {
  if (thinking) {
    return (
      <div className="flex justify-end">
        <div
          className="px-4 py-2.5 rounded-2xl rounded-ee-sm bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-sm"
          aria-label="النموذج يفكر..."
          role="status"
        >
          <span className="inline-flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" style={{ animationDelay: '300ms' }} />
          </span>
        </div>
      </div>
    );
  }

  if (role === 'user') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-es-sm bg-indigo-600 text-white text-sm">
          <p className="whitespace-pre-wrap">{text}</p>
          <div className="flex items-center justify-between mt-1 gap-3">
            {timestamp && (
              <p className="text-xs opacity-60">{formatTime(timestamp)}</p>
            )}
            {tokenCount !== undefined && (
              <span className="text-[10px] opacity-50 font-mono">
                {formatTokens(tokenCount)} tok
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-ee-sm bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 text-sm">
        <p className="whitespace-pre-wrap">{text}</p>
        <div className="flex items-center justify-between mt-1 gap-3">
          {timestamp && (
            <p className="text-xs text-slate-400">{formatTime(timestamp)}</p>
          )}
          {tokenCount !== undefined && (
            <span className="text-[10px] text-slate-400 font-mono">
              {formatTokens(tokenCount)} tok
            </span>
          )}
        </div>
      </div>
    </div>
  );
});
