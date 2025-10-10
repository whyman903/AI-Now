import { ensureSessionRegistered, getSessionId } from "./session";

const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";

const ANALYTICS_ENDPOINTS = {
  interaction: "/api/v1/analytics/track/interaction",
  search: "/api/v1/analytics/track/search",
} as const;

type AnalyticsEndpointKey = keyof typeof ANALYTICS_ENDPOINTS;

type Payload = Record<string, unknown>;

function sendAnalytics(endpoint: AnalyticsEndpointKey, payload: Payload) {
  const url = `${API_BASE}${ANALYTICS_ENDPOINTS[endpoint]}`;
  const body = JSON.stringify(payload);

  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    try {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(url, blob);
      return;
    } catch (error) {
      void error;
    }
  }

  if (typeof fetch === "function") {
    void fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body,
      keepalive: true,
    })
      .then((response) => {
        if (!response.ok) {
          response
            .json()
            .catch(() => ({}))
            .then((errorBody) => {
              console.error("Analytics request failed", {
                endpoint,
                status: response.status,
                body: errorBody,
                payload,
              });
            });
        }
      })
      .catch((error) => {
        console.error("Analytics request error", {
          endpoint,
          error,
          payload,
        });
      });
  }
}

export interface TrackContentInteractionOptions {
  position?: number;
  sourceName?: string;
  contentType?: string;
  sessionId?: string;
  userId?: string;
  metadata?: Record<string, unknown>;
}

export type TrackContentClickOptions = TrackContentInteractionOptions;

export function trackContentClick(contentId: string, options: TrackContentClickOptions = {}) {
  if (!contentId) {
    return;
  }

  const payload: Payload = {
    content_id: contentId,
    interaction_type: "click",
  };

  if (typeof options.position === "number") {
    payload.position = options.position;
  }

  const sessionId = options.sessionId ?? getSessionId();
  if (sessionId) {
    payload.session_id = sessionId;
  }

  if (options.userId) {
    payload.user_id = options.userId;
  }

  const sourcePage = typeof window !== "undefined" ? window.location.pathname : undefined;
  if (sourcePage) {
    payload.source_page = sourcePage;
  }

  const metadata: Payload = options.metadata ? { ...options.metadata } : {};

  if (options.sourceName) {
    metadata.source_name = options.sourceName;
  }

  if (options.contentType) {
    metadata.content_type = options.contentType;
  }

  if (Object.keys(metadata).length > 0) {
    payload.metadata = metadata;
  }

  if (sessionId) {
    ensureSessionRegistered({ sessionId });
  }

  sendAnalytics("interaction", payload);
}

export interface TrackSearchOptions {
  resultsCount?: number;
  sessionId?: string;
  userId?: string;
  filters?: Record<string, unknown>;
}

export function trackSearch(query: string, options: TrackSearchOptions = {}) {
  const trimmed = query.trim();
  if (!trimmed) {
    return;
  }

  const payload: Payload = {
    query: trimmed,
  };

  if (typeof options.resultsCount === "number") {
    payload.results_count = options.resultsCount;
  }

  const sessionId = options.sessionId ?? getSessionId();
  if (sessionId) {
    payload.session_id = sessionId;
  }

  if (options.userId) {
    payload.user_id = options.userId;
  }

  if (options.filters && Object.keys(options.filters).length > 0) {
    payload.filters = options.filters;
  }

  if (sessionId) {
    ensureSessionRegistered({ sessionId });
  }

  sendAnalytics("search", payload);
}

export type TrackContentViewOptions = TrackContentInteractionOptions;

export function trackContentView(contentId: string, options: TrackContentViewOptions = {}) {
  if (!contentId) {
    return;
  }

  const payload: Payload = {
    content_id: contentId,
    interaction_type: "view",
  };

  if (typeof options.position === "number") {
    payload.position = options.position;
  }

  const sessionId = options.sessionId ?? getSessionId();
  if (sessionId) {
    payload.session_id = sessionId;
  }

  if (options.userId) {
    payload.user_id = options.userId;
  }

  const sourcePage = typeof window !== "undefined" ? window.location.pathname : undefined;
  if (sourcePage) {
    payload.source_page = sourcePage;
  }

  const metadata: Payload = options.metadata ? { ...options.metadata } : {};

  if (options.sourceName) {
    metadata.source_name = options.sourceName;
  }

  if (options.contentType) {
    metadata.content_type = options.contentType;
  }

  if (Object.keys(metadata).length > 0) {
    payload.metadata = metadata;
  }

  if (sessionId) {
    ensureSessionRegistered({ sessionId });
  }

  sendAnalytics("interaction", payload);
}
