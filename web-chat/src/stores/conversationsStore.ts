import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message } from '@/lib/types';

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  totalTokens: number;
  createdAt: number;
  updatedAt: number;
}

interface ConversationsState {
  conversations: Conversation[];
  activeId: string | null;

  createConversation: () => string;
  selectConversation: (id: string) => void;
  addMessage: (convId: string, msg: Message) => void;
  updateTotalTokens: (convId: string, delta: number) => void;
  deleteConversation: (id: string) => void;
  clearActive: () => void;
  getActive: () => Conversation | undefined;
}

function makeId(): string {
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function makeTitle(firstUserText: string): string {
  const trimmed = firstUserText.trim();
  return trimmed.length > 45 ? trimmed.slice(0, 42) + '…' : trimmed;
}

export const useConversationsStore = create<ConversationsState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeId: null,

      createConversation: () => {
        const id = makeId();
        const conv: Conversation = {
          id,
          title: 'محادثة جديدة',
          messages: [],
          totalTokens: 0,
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((s) => ({ conversations: [conv, ...s.conversations], activeId: id }));
        return id;
      },

      // Pass '' or null to deselect (e.g. after "New Chat" before first message)
      selectConversation: (id) => set({ activeId: id || null }),

      addMessage: (convId, msg) =>
        set((s) => ({
          conversations: s.conversations.map((c) => {
            if (c.id !== convId) return c;
            const messages = [...c.messages, msg];
            // Set title from first user message
            const title =
              c.messages.length === 0 && msg.role === 'user'
                ? makeTitle(msg.text)
                : c.title;
            return { ...c, messages, title, updatedAt: Date.now() };
          }),
        })),

      updateTotalTokens: (convId, delta) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? { ...c, totalTokens: Math.max(0, c.totalTokens + delta) }
              : c,
          ),
        })),

      deleteConversation: (id) =>
        set((s) => {
          const conversations = s.conversations.filter((c) => c.id !== id);
          const activeId = s.activeId === id
            ? (conversations[0]?.id ?? null)
            : s.activeId;
          return { conversations, activeId };
        }),

      clearActive: () => set({ activeId: null }),

      getActive: () => {
        const { conversations, activeId } = get();
        return conversations.find((c) => c.id === activeId);
      },
    }),
    {
      name: 'ws-conversations',
      // Only persist conversations array + activeId, not function refs
      partialize: (s) => ({ conversations: s.conversations, activeId: s.activeId }),
    },
  ),
);
