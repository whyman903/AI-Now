const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";
const SESSION_ENDPOINT = `${API_BASE}/api/v1/analytics/session`;

const SESSION_ID_STORAGE_KEY = "ai-now:session-id";
const SESSION_REGISTERED_AT_KEY = "ai-now:session-registered-at";
const SESSION_REFRESH_INTERVAL_MS = 5 * 60 * 1000; // refresh registration at most every 5 minutes

let registrationInFlight: Promise<void> | null = null;

const isBrowser = () => typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const readStorage = (key: string): string | null => {
  if (!isBrowser()) return null;
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    console.warn("Unable to read from localStorage", error);
    return null;
  }
};

const writeStorage = (key: string, value: string) => {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn("Unable to write to localStorage", error);
  }
};

const now = () => (typeof Date !== "undefined" ? Date.now() : 0);

const generateSessionId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${now()}-${Math.random().toString(36).slice(2, 11)}`;
};

const registerSession = (sessionId: string, force: boolean) => {
  if (!isBrowser()) return;

  const lastRegisteredRaw = readStorage(SESSION_REGISTERED_AT_KEY);
  const lastRegisteredAt = lastRegisteredRaw ? Number(lastRegisteredRaw) : 0;

  if (!force && lastRegisteredAt && now() - lastRegisteredAt < SESSION_REFRESH_INTERVAL_MS) {
    return;
  }

  if (registrationInFlight) {
    return;
  }

  const body = JSON.stringify({ session_id: sessionId });

  registrationInFlight = fetch(SESSION_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
    keepalive: true,
  })
    .then(() => {
      writeStorage(SESSION_REGISTERED_AT_KEY, String(now()));
    })
    .catch((error) => {
      console.warn("Failed to register analytics session", error);
    })
    .finally(() => {
      registrationInFlight = null;
    });
};

export const getSessionId = (): string | null => {
  if (!isBrowser()) return null;

  let sessionId = readStorage(SESSION_ID_STORAGE_KEY);
  if (sessionId) {
    return sessionId;
  }

  sessionId = generateSessionId();
  writeStorage(SESSION_ID_STORAGE_KEY, sessionId);

  // Immediately register a brand-new session
  setTimeout(() => registerSession(sessionId, true), 0);

  return sessionId;
};

interface EnsureOptions {
  force?: boolean;
  sessionId?: string;
}

export const ensureSessionRegistered = (options: EnsureOptions = {}): void => {
  if (!isBrowser()) return;
  const sessionId = options.sessionId ?? getSessionId();
  if (!sessionId) return;
  registerSession(sessionId, Boolean(options.force));
};
