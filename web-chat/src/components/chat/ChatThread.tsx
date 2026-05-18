import { useEffect, useRef } from 'react';
import type { Message } from '@/lib/types';
import { MessageBubble } from './MessageBubble';
import { AgentRunCard } from '@/components/skill-cards/AgentRunCard';
import { EmptyState } from './EmptyState';

interface ChatThreadProps {
  messages: Message[];
  onChip: (text: string) => void;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

export function ChatThread({ messages, onChip, onSuggestion, onContinue, onEnd }: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  if (messages.length === 0) {
    return <EmptyState onChip={onChip} />;
  }

  return (
    <div className="chat-column py-6 space-y-4">
      {messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <MessageBubble
              key={msg.id}
              role="user"
              text={msg.text}
              timestamp={msg.timestamp}
            />
          );
        }

        if (msg.taskId) {
          return (
            <AgentRunCard
              key={msg.id}
              taskId={msg.taskId}
              goal={msg.text}
              skill={msg.skillHint}
              onSuggestion={onSuggestion}
              onContinue={onContinue}
              onEnd={onEnd}
            />
          );
        }

        return (
          <MessageBubble
            key={msg.id}
            role="assistant"
            text={msg.text}
            timestamp={msg.timestamp}
          />
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
