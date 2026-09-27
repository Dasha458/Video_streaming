import { createContext } from "react";
import type { UserInfo } from "@/lib/api/types";

export interface AuthContextType {
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<UserInfo | null>;
}

/** Lives apart from the provider and the hook so that neither file mixes a
 *  component export with a plain one -- which is what breaks Fast Refresh. */
export const AuthContext = createContext<AuthContextType | null>(null);
