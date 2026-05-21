import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SavedDesign {
  id: string;
  name: string;
  filename: string;
  content: string; // full HTML — stored in localStorage for offline preview
  taskId: string;
  createdAt: number;
}

interface SavedDesignsState {
  designs: SavedDesign[];
  addDesign: (d: Omit<SavedDesign, 'id' | 'createdAt'>) => void;
  renameDesign: (id: string, name: string) => void;
  deleteDesign: (id: string) => void;
}

export const useSavedDesignsStore = create<SavedDesignsState>()(
  persist(
    (set) => ({
      designs: [],

      addDesign: (d) =>
        set((s) => ({
          designs: [
            {
              ...d,
              id: crypto.randomUUID(),
              createdAt: Date.now(),
            },
            ...s.designs,
          ],
        })),

      renameDesign: (id, name) =>
        set((s) => ({
          designs: s.designs.map((d) => (d.id === id ? { ...d, name } : d)),
        })),

      deleteDesign: (id) =>
        set((s) => ({ designs: s.designs.filter((d) => d.id !== id) })),
    }),
    { name: 'ws-saved-designs' },
  ),
);
