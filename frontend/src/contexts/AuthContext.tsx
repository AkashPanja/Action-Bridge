import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { LoginResponse, User } from "../types";

const API_BASE = "/api/v1";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  setupRequired: boolean;
  login: (email: string, password: string) => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  confirmPasswordReset: (token: string, newPassword: string) => Promise<void>;
  completeSetup: (name: string, email: string, password: string, smtp?: Record<string, unknown>, companyName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_KEY = "doc_action_token";
const USER_KEY = "doc_action_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const statusRes = await fetch(`${API_BASE}/auth/status`);
        if (statusRes.ok) {
          const status = await statusRes.json();
          if (status.setup_required) {
            setSetupRequired(true);
            setIsLoading(false);
            return;
          }
        }
      } catch {
        // offline or server not ready
      }

      const savedToken = localStorage.getItem(TOKEN_KEY);
      const savedUser = localStorage.getItem(USER_KEY);
      if (savedToken && savedUser) {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      }
      setIsLoading(false);
    })();
  }, []);

  async function login(email: string, password: string) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(err.detail);
    }
    const data: LoginResponse = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    setToken(data.access_token);
    setUser(data.user);
  }

  async function requestPasswordReset(email: string) {
    const res = await fetch(`${API_BASE}/auth/password-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail);
    }
  }

  async function confirmPasswordReset(token: string, newPassword: string) {
    const res = await fetch(`${API_BASE}/auth/password-reset/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Reset failed" }));
      throw new Error(err.detail);
    }
  }

  async function completeSetup(name: string, email: string, password: string, smtp?: Record<string, unknown>, companyName?: string) {
    const body: Record<string, unknown> = { name, email, password };
    body.company_name = companyName || "Action Bridge";
    if (smtp) Object.assign(body, smtp);
    const res = await fetch(`${API_BASE}/auth/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Setup failed" }));
      throw new Error(err.detail);
    }
    const data: LoginResponse = await res.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    setToken(data.access_token);
    setUser(data.user);
    setSetupRequired(false);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, isLoading, setupRequired, login, requestPasswordReset, confirmPasswordReset, completeSetup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function getAuthHeaders(token: string | null): Record<string, string> {
  if (token) return { Authorization: `Bearer ${token}` };
  return {};
}
