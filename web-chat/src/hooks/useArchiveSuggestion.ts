import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';

export interface ArchiveSuggestion {
  task_id: string;
  goal: string;
  summary: string;
  score: number;
}

const MIN_QUERY_LEN = 12;
const SCORE_THRESHOLD = 0.55;
const DEBOUNCE_MS = 1000;

export function useArchiveSuggestion(query: string): ArchiveSuggestion | null {
  const [suggestion, setSuggestion] = useState<ArchiveSuggestion | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastQuery = useRef('');

  useEffect(() => {
    if (query.trim().length < MIN_QUERY_LEN) {
      setSuggestion(null);
      return;
    }

    if (timer.current) clearTimeout(timer.current);

    timer.current = setTimeout(async () => {
      if (query === lastQuery.current) return;
      lastQuery.current = query;
      try {
        const data = await apiFetch<{ matches: ArchiveSuggestion[] }>(
          `/api/archive/search?q=${encodeURIComponent(query)}`,
        );
        const top = data.matches?.[0];
        if (top && typeof top.score === 'number' && top.score >= SCORE_THRESHOLD) {
          setSuggestion(top);
        } else {
          setSuggestion(null);
        }
      } catch {
        setSuggestion(null);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query]);

  // Clear suggestion when query is cleared
  useEffect(() => {
    if (!query.trim()) setSuggestion(null);
  }, [query]);

  return suggestion;
}
