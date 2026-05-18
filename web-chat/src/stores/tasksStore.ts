import { create } from 'zustand';

export interface TaskRecord {
  taskId: string;
  pipelineId?: string;
  goal: string;
  skill?: string;
  status: 'running' | 'succeeded' | 'failed' | 'cancelled';
  startedAt: number;
  completedAt?: number;
  summaryAr?: string;
}

interface TasksState {
  tasks: TaskRecord[];
  activeTaskId: string | null;
  addTask: (task: TaskRecord) => void;
  updateTask: (taskId: string, patch: Partial<TaskRecord>) => void;
  setActive: (taskId: string | null) => void;
}

export const useTasksStore = create<TasksState>()((set) => ({
  tasks: [],
  activeTaskId: null,
  addTask: (task) => set((s) => ({ tasks: [task, ...s.tasks] })),
  updateTask: (taskId, patch) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.taskId === taskId ? { ...t, ...patch } : t)),
    })),
  setActive: (taskId) => set({ activeTaskId: taskId }),
}));
