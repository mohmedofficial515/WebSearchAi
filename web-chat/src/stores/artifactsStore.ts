import { create } from 'zustand';
import type { ArtifactMeta } from '@/lib/events';

interface ArtifactsState {
  artifacts: Record<string, ArtifactMeta>;
  taskArtifacts: Record<string, string[]>; // taskId → artifact_id[]
  addArtifact: (taskId: string, artifact: ArtifactMeta) => void;
}

export const useArtifactsStore = create<ArtifactsState>()((set) => ({
  artifacts: {},
  taskArtifacts: {},
  addArtifact: (taskId, artifact) =>
    set((s) => ({
      artifacts: { ...s.artifacts, [artifact.artifact_id]: artifact },
      taskArtifacts: {
        ...s.taskArtifacts,
        [taskId]: [...(s.taskArtifacts[taskId] ?? []), artifact.artifact_id],
      },
    })),
}));
