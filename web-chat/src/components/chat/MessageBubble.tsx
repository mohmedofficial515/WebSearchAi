import { memo } from 'react';
import { formatTokens } from '@/lib/tokens';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  text: string;
  timestamp?: number;
  tokenCount?: number;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
}

export const MessageBubble = memo(function MessageBubble({
  role,
  text,
  timestamp,
  tokenCount,
}: MessageBubbleProps) {
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
