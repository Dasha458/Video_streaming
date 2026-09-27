import { useEffect, useState, useCallback, type ReactNode } from "react";
import type { UserInfo } from "@/lib/api/types";
import { AuthContext } from "./auth-context";
import {
  loginUser as apiLogin,
  registerUser as apiRegister,
  logoutUser as apiLogout,
  getCurrentUser,
} from "@api/authApi";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // The session cookie is httpOnly, so the only way to know whether we're
  // logged in is to ask the backend; a 401 here simply means "no session".
  const refreshUser = useCallback(async (): Promise<UserInfo | null> => {
    try {
      const userData = await getCurrentUser();
      setUser(userData);
      return userData;
    } catch {
      setUser(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      await refreshUser();
    },
    [refreshUser],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await apiRegister(email, password);
      await apiLogin(email, password); // auto-login: backend sets the session cookie
      await refreshUser();
    },
    [refreshUser],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
