import { createContext, useContext, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import * as api from "./api";

interface AuthContextValue {
  username: string | null;
  loggedIn: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(api.getUsername());

  async function login(user: string, password: string) {
    const res = await api.login(user, password);
    api.saveSession(res.access_token, res.username);
    setUsername(res.username);
  }

  async function register(user: string, password: string) {
    const res = await api.register(user, password);
    api.saveSession(res.access_token, res.username);
    setUsername(res.username);
  }

  function logout() {
    api.clearSession();
    setUsername(null);
  }

  const value: AuthContextValue = {
    username,
    loggedIn: username !== null && api.isLoggedIn(),
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

/** Route guard: redirects to /login (remembering where the user was headed)
 * whenever there's no valid, unexpired session token. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { loggedIn } = useAuth();
  const location = useLocation();

  if (!loggedIn) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
