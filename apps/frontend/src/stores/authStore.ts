import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Role = "admin" | "operator" | "viewer";

export interface AuthUser {
  id: string;
  username: string;
  role: Role;
  created_at: number;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  setSession: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      setUser: (user) => set({ user }),
      clear: () => set({ token: null, user: null }),
    }),
    { name: "auth" },
  ),
);

export function getAuthToken(): string | null {
  return useAuthStore.getState().token;
}
