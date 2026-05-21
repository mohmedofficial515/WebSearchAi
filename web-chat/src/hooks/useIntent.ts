import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { IntentResponse } from '@/lib/api';

export type { IntentResponse };

const DEBOUNCE_MS = 800;

export function useIntent(message: string): IntentResponse | null {
  const [result, setResult] = useState<IntentResponse | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();

    if (!message.trim() || message.trim().length < 4 || message.startsWith('/')) {
      setResult(null);
      return;
    }

    timerRef.current = setTimeout(async () => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const res = await apiFetch<IntentResponse>('/api/intent', {
          method: 'POST',
          body: JSON.stringify({ message }),
          signal: ctrl.signal,
        });
        setResult(res);
      } catch {
        // ignore abort / network errors
      }
    }, DEBOUNCE_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [message]);

  return result;
}
