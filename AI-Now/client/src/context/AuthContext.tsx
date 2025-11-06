import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";

export interface AuthUser {
  id: string;
  email: string;
  display_name?: string | null;
  displayName?: string | null;
}

export interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticating: boolean;
  authError: string | null;
  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string, displayName?: string | null) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
  getAccessToken: () => string | null;
  fetchWithAuth: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export { AuthContext };

type AuthProviderProps = {
  children: ReactNode;
};

const parseError = async (response: Response): Promise<string> => {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data?.detail) && data.detail.length) {
      const first = data.detail[0] as { msg?: string };
      if (first?.msg) {
        return first.msg;
      }
    }
  } catch {
    // fall through
  }
  return `${response.status}: ${response.statusText}`;
};

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  const refreshAccessToken = useCallback(async (): Promise<string | null> => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        setAccessToken(null);
        return null;
      }
      const data = (await response.json()) as { access_token: string };
      if (data.access_token) {
        setAccessToken(data.access_token);
        return data.access_token;
      }
      setAccessToken(null);
      return null;
    } catch (error) {
      console.warn("Failed to refresh access token", error);
      setAccessToken(null);
      return null;
    }
  }, []);

  const fetchSession = useCallback(async () => {
    setIsLoading(true);
    try {
      let token = accessToken;
      
      if (!token) {
        token = await refreshAccessToken();
      }
      
      const headers: HeadersInit = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
      
      const response = await fetch(`${API_BASE}/api/v1/auth/session`, {
        method: "GET",
        credentials: "include",
        headers,
      });
      if (!response.ok) {
        if (response.status !== 401) {
          console.warn("Session check failed", response.status, response.statusText);
        }
        setAccessToken(null);
        setUser(null);
        return;
      }
      const data = (await response.json()) as { user: AuthUser | null };
      setUser(
        data.user
          ? {
              ...data.user,
              displayName: data.user.display_name ?? data.user.displayName ?? null,
            }
          : null,
      );
    } catch (error) {
      console.warn("Failed to fetch session", error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, refreshAccessToken]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  const login = useCallback(async (email: string, password: string) => {
    setIsAuthenticating(true);
    setAuthError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const message = await parseError(response);
        setAuthError(message);
        return false;
      }
      const data = (await response.json()) as { user: AuthUser | null; access_token: string };
      if (data.access_token) {
        setAccessToken(data.access_token);
      } else {
        setAccessToken(null);
      }
      setUser(
        data.user
          ? { ...data.user, displayName: data.user.display_name ?? data.user.displayName ?? null }
          : null,
      );
      return true;
    } catch (error) {
      console.error("Login failed", error);
      setAuthError("Unable to sign in. Please try again.");
      return false;
    } finally {
      setIsAuthenticating(false);
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string | null) => {
      setIsAuthenticating(true);
      setAuthError(null);
      try {
        const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email, password, display_name: displayName ?? null }),
        });
        if (!response.ok) {
          const message = await parseError(response);
          setAuthError(message);
          return false;
        }
        const data = (await response.json()) as { user: AuthUser | null; access_token: string };
        if (data.access_token) {
          setAccessToken(data.access_token);
        } else {
          setAccessToken(null);
        }
        setUser(
          data.user
            ? { ...data.user, displayName: data.user.display_name ?? data.user.displayName ?? null }
            : null,
        );
        return true;
      } catch (error) {
        console.error("Registration failed", error);
        setAuthError("Unable to create account. Please try again.");
        return false;
      } finally {
        setIsAuthenticating(false);
      }
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (error) {
      console.warn("Logout failed", error);
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const clearError = useCallback(() => setAuthError(null), []);

  const getAccessToken = useCallback(() => {
    return accessToken;
  }, [accessToken]);

  const fetchWithAuth = useCallback(
    async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const execute = async (token: string | null) => {
        const headers = new Headers(init.headers ?? {});
        if (token) {
          headers.set("Authorization", `Bearer ${token}`);
        }
        const requestInit: RequestInit = {
          ...init,
          headers,
          credentials: init.credentials ?? "include",
        };
        return fetch(input, requestInit);
      };

      let token = accessToken;
      if (!token) {
        token = await refreshAccessToken();
      }

      let response = await execute(token);
      if (response.status === 401) {
        token = await refreshAccessToken();
        if (token) {
          response = await execute(token);
        }
      }

      if (response.status === 401) {
        setAccessToken(null);
        setUser(null);
      }

      return response;
    },
    [accessToken, refreshAccessToken],
  );

  const value: AuthContextValue = useMemo(
    () => ({
      user,
      isLoading,
      isAuthenticating,
      authError,
      login,
      register,
      logout,
      clearError,
      getAccessToken,
      fetchWithAuth,
    }),
    [user, isLoading, isAuthenticating, authError, login, register, logout, clearError, getAccessToken, fetchWithAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
