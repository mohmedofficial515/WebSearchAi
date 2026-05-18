import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
import { MarkdownArtifactCard } from '@/components/skill-cards/MarkdownArtifactCard';
import { HtmlArtifactCard } from '@/components/skill-cards/HtmlArtifactCard';
import { CodeArtifactCard } from '@/components/skill-cards/CodeArtifactCard';
import { MermaidArtifactCard } from '@/components/skill-cards/MermaidArtifactCard';
import { PdfArtifactCard } from '@/components/skill-cards/PdfArtifactCard';
import { SummarizeCard } from '@/components/skill-cards/SummarizeCard';
import { TranslateCard } from '@/components/skill-cards/TranslateCard';
import { CompetitorMatrixCard } from '@/components/skill-cards/CompetitorMatrixCard';
import { PipelineCard } from '@/components/pipeline/PipelineCard';
import { EmptyState } from './EmptyState';

const msgVariants = {
  hidden: { opacity: 0, y: 14 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 0.1, 0.25, 1] as const } },
  exit:   { opacity: 0, transition: { duration: 0.12 } },
};

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
    case 'md_writer':
      return <MarkdownArtifactCard {...props} />;
    case 'html_artifact':
      return <HtmlArtifactCard {...props} />;
    case 'code_artifact':
      return <CodeArtifactCard {...props} />;
    case 'mermaid_diagram':
      return <MermaidArtifactCard {...props} />;
    case 'pdf_export':
      return <PdfArtifactCard {...props} />;
    case 'summarize':
      return <SummarizeCard {...props} />;
    case 'translate':
      return <TranslateCard {...props} />;
    case 'competitor_matrix':
      return <CompetitorMatrixCard {...props} />;
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
      <AnimatePresence initial={false}>
        {messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <motion.div key={msg.id} variants={msgVariants} initial="hidden" animate="show" exit="exit">
                <MessageBubble role="user" text={msg.text} timestamp={msg.timestamp} />
              </motion.div>
            );
          }

          if (msg.pipelineId) {
            return (
              <motion.div key={msg.id} variants={msgVariants} initial="hidden" animate="show" exit="exit">
                <PipelineCard
                  pipelineId={msg.pipelineId}
                  goal={msg.text}
                  initialPlan={msg.pipelineData}
                  onSuggestion={onSuggestion}
                  onContinue={onContinue}
                  onEnd={onEnd}
                />
              </motion.div>
            );
          }

          if (msg.taskId) {
            return (
              <motion.div key={msg.id} variants={msgVariants} initial="hidden" animate="show" exit="exit">
                <SkillCard
                  taskId={msg.taskId}
                  goal={msg.text}
                  skill={msg.skillHint}
                  onSuggestion={onSuggestion}
                  onContinue={onContinue}
                  onEnd={onEnd}
                />
              </motion.div>
            );
          }

          return (
            <motion.div key={msg.id} variants={msgVariants} initial="hidden" animate="show" exit="exit">
              <MessageBubble role="assistant" text={msg.text} timestamp={msg.timestamp} />
            </motion.div>
          );
        })}
      </AnimatePresence>
      <div ref={bottomRef} />
    </div>
  );
}
