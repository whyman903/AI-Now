import { useCallback, useEffect, useMemo, useRef } from "react";

type NullableHTMLElement = HTMLElement | null;
type Threshold = number | number[];

interface UseViewTrackingOptions {
  /** Intersection ratio threshold that triggers the view callback. Defaults to 0.4 */
  threshold?: Threshold;
  /** Root margin applied to the observer */
  rootMargin?: string;
  /** When false, view tracking is disabled and no observers are attached. Defaults to true. */
  enabled?: boolean;
}

interface ObserverRegistryEntry {
  observer: IntersectionObserver;
  targets: Map<Element, (entry: IntersectionObserverEntry) => void>;
  threshold: Threshold;
  rootMargin: string;
}

const OBSERVER_REGISTRY = new Map<string, ObserverRegistryEntry>();

const normalizeThresholdKey = (threshold: Threshold) =>
  Array.isArray(threshold) ? threshold.join(",") : `${threshold}`;

function ensureObserverEntry(
  key: string,
  threshold: Threshold,
  rootMargin: string
): ObserverRegistryEntry {
  let entry = OBSERVER_REGISTRY.get(key);
  if (!entry) {
    const targets = new Map<Element, (entry: IntersectionObserverEntry) => void>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const item of entries) {
          if (!item.isIntersecting) {
            continue;
          }

          const callback = targets.get(item.target);
          if (callback) {
            callback(item);
          }
        }
      },
      { threshold, rootMargin }
    );

    entry = { observer, targets, threshold, rootMargin };
    OBSERVER_REGISTRY.set(key, entry);
  }

  return entry;
}

export function useViewTracking(
  onView: () => void,
  options: UseViewTrackingOptions = {}
) {
  const hasTrackedRef = useRef(false);
  const observedElementRef = useRef<NullableHTMLElement>(null);
  const activeObserverKeyRef = useRef<string | null>(null);
  const latestCallbackRef = useRef(onView);

  useEffect(() => {
    latestCallbackRef.current = onView;
  }, [onView]);

  const threshold = options.threshold ?? 0.4;
  const rootMargin = options.rootMargin ?? "0px";
  const enabled = options.enabled ?? true;

  const observerKey = useMemo(
    () => `${normalizeThresholdKey(threshold)}|${rootMargin}`,
    [rootMargin, threshold]
  );

  const cleanup = useCallback(() => {
    const node = observedElementRef.current;
    const observerKeyFromRef = activeObserverKeyRef.current;
    if (!node || !observerKeyFromRef) {
      return;
    }

    const entry = OBSERVER_REGISTRY.get(observerKeyFromRef);
    if (entry) {
      entry.targets.delete(node);
      entry.observer.unobserve(node);
      if (entry.targets.size === 0) {
        entry.observer.disconnect();
        OBSERVER_REGISTRY.delete(observerKeyFromRef);
      }
    }

    observedElementRef.current = null;
    activeObserverKeyRef.current = null;
  }, []);

  useEffect(() => {
    if (!enabled) {
      cleanup();
      observedElementRef.current = null;
      activeObserverKeyRef.current = null;
    }
  }, [cleanup, enabled]);

  const handleIntersect = useCallback(
    (_entry: IntersectionObserverEntry) => {
      if (hasTrackedRef.current) {
        return;
      }

      hasTrackedRef.current = true;
      cleanup();
      latestCallbackRef.current?.();
    },
    [cleanup]
  );

  const observe = useCallback(
    (node: NullableHTMLElement) => {
      if (!enabled) {
        if (!node) {
          cleanup();
        }
        return;
      }

      if (hasTrackedRef.current) {
        if (!node) {
          cleanup();
        }
        return;
      }

      if (!node) {
        if (observedElementRef.current) {
          cleanup();
        }
        return;
      }

      if (observedElementRef.current === node) {
        return;
      }

      if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") {
        if (!hasTrackedRef.current) {
          hasTrackedRef.current = true;
          latestCallbackRef.current?.();
        }
        observedElementRef.current = null;
        activeObserverKeyRef.current = null;
        return;
      }

      if (observedElementRef.current) {
        cleanup();
      }

      const entry = ensureObserverEntry(observerKey, threshold, rootMargin);
      entry.targets.set(node, handleIntersect);
      entry.observer.observe(node);

      observedElementRef.current = node;
      activeObserverKeyRef.current = observerKey;
    },
    [cleanup, enabled, handleIntersect, observerKey, rootMargin, threshold]
  );

  useEffect(() => () => cleanup(), [cleanup]);

  return observe;
}
