import { memo, useEffect, useRef, useState } from 'react';
import { formatTokens } from '@/lib/tokens';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  text: string;
  timestamp?: number;
  tokenCount?: number;
  thinking?: boolean;
  /** Animate text reveal (only for new assistant messages) */
  isNew?: boolean;
}

const TYPING_SPEED_MS = 8; // ms per character — fast but visible

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
}

function useTypingText(text: string, isNew: boolean): { displayed: string; done: boolean } {
  const [displayed, setDisplayed] = useState(() => (isNew ? '' : text));
  const [done, setDone] = useState(!isNew);
  const prevTextRef = useRef(text);

  useEffect(() => {
    // If text changed without isNew (e.g. store update), sync immediately
    if (!isNew || prevTextRef.current !== text) {
      prevTextRef.current = text;
      if (!isNew) {
        setDisplayed(text);
        setDone(true);
        return;
      }
    }

    if (!isNew || !text) {
      setDisplayed(text);
      setDone(true);
      return;
    }

    setDisplayed('');
    setDone(false);
    let i = 0;
    const id = setInterval(() => {
      i += 2; // reveal 2 chars per tick for responsiveness
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(id);
        setDisplayed(text);
        setDone(true);
      }
    }, TYPING_SPEED_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, isNew]);

  return { displayed, done };
}

export const MessageBubble = memo(function MessageBubble({
  role,
  text,
  timestamp,
  tokenCount,
  thinking = false,
  isNew = false,
}: MessageBubbleProps) {
  const { displayed } = useTypingText(text, role === 'assistant' && isNew);

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
        <p className="whitespace-pre-wrap">
          {displayed}
          {isNew && displayed.length < text.length && (
            <span className="inline-block w-0.5 h-3.5 bg-indigo-500 animate-pulse ml-0.5 align-text-bottom" />
          )}
        </p>
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
