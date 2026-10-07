import { create } from "zustand";

export type SessionUser = {
  userId: string;
  email: string;
};

type SessionState = {
  /** JWT — module memory only. Never localStorage/sessionStorage/cookie. */
  token: string | null;
  user: SessionUser | null;
  activeWorkspaceId: string | null;
  setSession: (token: string, user: SessionUser) => void;
  clearSession: () => void;
  setActiveWorkspaceId: (id: string | null) => void;
};

export const useSession = create<SessionState>((set) => ({
  token: null,
  user: null,
  activeWorkspaceId: null,
  setSession: (token, user) => set({ token, user }),
  clearSession: () => set({ token: null, user: null }),
  setActiveWorkspaceId: (activeWorkspaceId) => set({ activeWorkspaceId }),
}));