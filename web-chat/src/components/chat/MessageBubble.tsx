interface MessageBubbleProps {
  role: 'user' | 'assistant';
  text: string;
  timestamp?: number;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ role, text, timestamp }: MessageBubbleProps) {
  if (role === 'user') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-es-sm bg-indigo-600 text-white text-sm">
          <p className="whitespace-pre-wrap">{text}</p>
          {timestamp && (
            <p className="text-xs opacity-60 mt-1 text-end">{formatTime(timestamp)}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-ee-sm bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 text-sm">
        <p className="whitespace-pre-wrap">{text}</p>
        {timestamp && (
          <p className="text-xs text-slate-400 mt-1 text-start">{formatTime(timestamp)}</p>
        )}
      </div>
    </div>
  );
}
