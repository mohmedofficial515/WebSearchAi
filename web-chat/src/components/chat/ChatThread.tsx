import { useEffect, useRef } from 'react';
import type { Message } from '@/lib/types';
import { MessageBubble } from './MessageBubble';
import { AgentRunCard } from '@/components/skill-cards/AgentRunCard';
import { SearchResultCard } from '@/components/skill-cards/SearchResultCard';
import { ExploreReportCard } from '@/components/skill-cards/ExploreReportCard';
import { DesignTokensCard } from '@/components/skill-cards/DesignTokensCard';
import { ComponentsGalleryCard } from '@/components/skill-cards/ComponentsGalleryCard';
import { LoginCard } from '@/components/skill-cards/LoginCard';
import { SignupCard } from '@/components/skill-cards/SignupCard';
import { TempSignupCard } from '@/components/skill-cards/TempSignupCard';
import { CloneCard } from '@/components/skill-cards/CloneCard';
import { SiteCloneCard } from '@/components/skill-cards/SiteCloneCard';
import { EmptyState } from './EmptyState';

interface ChatThreadProps {
  messages: Message[];
  onChip: (text: string) => void;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

interface SkillCardProps {
  taskId: string;
  goal: string;
  skill?: string;
  onSuggestion: (prompt: string) => void;
  onContinue: () => void;
  onEnd: () => void;
}

function SkillCard({ taskId, goal, skill, onSuggestion, onContinue, onEnd }: SkillCardProps) {
  const props = { taskId, goal, onSuggestion, onContinue, onEnd };

  switch (skill) {
    case 'research':
    case 'summarize':
      return <SearchResultCard {...props} />;
    case 'explore':
      return <ExploreReportCard {...props} />;
    case 'design_tokens':
      return <DesignTokensCard {...props} />;
    case 'components':
    case 'find_components':
      return <ComponentsGalleryCard {...props} />;
    case 'login':
      return <LoginCard {...props} />;
    case 'signup':
      return <SignupCard {...props} />;
    case 'temp_signup':
      return <TempSignupCard {...props} />;
    case 'clone':
      return <CloneCard {...props} />;
    case 'site_clone':
      return <SiteCloneCard {...props} />;
    default:
      return <AgentRunCard {...props} skill={skill} />;
  }
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
            <SkillCard
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
