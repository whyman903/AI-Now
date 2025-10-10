import { useCallback, useEffect, useRef } from "react";

type NullableHTMLElement = HTMLElement | null;

interface UseViewTrackingOptions {
  /** Intersection ratio threshold that triggers the view callback. Defaults to 0.4 */
  threshold?: number;
  /** Root margin applied to the observer */
  rootMargin?: string;
}

export function useViewTracking(
  onView: () => void,
  options: UseViewTrackingOptions = {}
) {
  const hasTrackedRef = useRef(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const disconnect = useCallback(() => {
    observerRef.current?.disconnect();
    observerRef.current = null;
  }, []);

  const threshold = options.threshold ?? 0.4;
  const rootMargin = options.rootMargin ?? "0px";

  const observe = useCallback(
    (node: NullableHTMLElement) => {
      if (hasTrackedRef.current) {
        return;
      }

      if (!node) {
        disconnect();
        return;
      }

      if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") {
        hasTrackedRef.current = true;
        onView();
        return;
      }

      disconnect();

      observerRef.current = new IntersectionObserver((entries) => {
        if (hasTrackedRef.current) {
          disconnect();
          return;
        }

        const isVisible = entries.some((entry) => entry.isIntersecting);
        if (isVisible) {
          hasTrackedRef.current = true;
          disconnect();
          onView();
        }
      }, { threshold, rootMargin });

      observerRef.current.observe(node);
    },
    [disconnect, onView, rootMargin, threshold]
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return observe;
}
