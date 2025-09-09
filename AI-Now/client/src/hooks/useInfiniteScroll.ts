import { useEffect, useRef, useState } from "react";

interface UseInfiniteScrollOptions {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  rootMargin?: string;
  threshold?: number;
  // When true, do not auto-load more until the user scrolls/interacts
  requireUserScroll?: boolean;
  // Minimum time between loads while sentinel remains visible
  cooldownMs?: number;
}

export function useInfiniteScroll({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  rootMargin = "0px 0px 200px 0px",
  threshold = 0.1,
  requireUserScroll = true,
  cooldownMs = 700,
}: UseInfiniteScrollOptions) {
  const [targetElement, setTargetElement] = useState<Element | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const [activated, setActivated] = useState<boolean>(!requireUserScroll);
  const [rootEl, setRootEl] = useState<Element | null>(null);
  const wasIntersectingRef = useRef<boolean>(false);
  const userGestureSinceLastLoadRef = useRef<boolean>(false);
  const lastLoadAtRef = useRef<number>(0);

  // Find the nearest scrollable ancestor to use as the IO root
  useEffect(() => {
    if (!targetElement) return;
    const getScrollableAncestor = (el: Element | null): Element | null => {
      let node: Element | null = el?.parentElement || null;
      while (node) {
        const style = window.getComputedStyle(node as Element);
        const overflowY = style.getPropertyValue("overflow-y");
        const overflow = style.getPropertyValue("overflow");
        const isScrollable = [overflowY, overflow].some((v) => v === "auto" || v === "scroll");
        if (isScrollable && (node as HTMLElement).scrollHeight > (node as HTMLElement).clientHeight) {
          return node;
        }
        node = node.parentElement;
      }
      return null;
    };
    const ancestor = getScrollableAncestor(targetElement as Element);
    setRootEl(ancestor);
  }, [targetElement]);

  // Activate infinite loading on first user interaction (wheel/touch/scroll/keys)
  useEffect(() => {
    if (!requireUserScroll) return;
    const onGesture = () => {
      if (!activated) setActivated(true);
      userGestureSinceLastLoadRef.current = true;
    };
    const keyHandler = (e: KeyboardEvent) => {
      const keys = ["PageDown", "End", "ArrowDown", "Space"];
      if (keys.includes(e.key)) onGesture();
    };

    // Prefer listening on the scroll root if present; fall back to window/document
    const scrollTarget: any = rootEl || window;
    scrollTarget.addEventListener("wheel", onGesture, { passive: true });
    scrollTarget.addEventListener("touchmove", onGesture, { passive: true });
    document.addEventListener("keydown", keyHandler);

    return () => {
      try { scrollTarget.removeEventListener("wheel", onGesture as any); } catch {}
      try { scrollTarget.removeEventListener("touchmove", onGesture as any); } catch {}
      document.removeEventListener("keydown", keyHandler);
    };
  }, [requireUserScroll, rootEl, activated]);

  useEffect(() => {
    if (!targetElement) return;

    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        const isNowIntersecting = entry.isIntersecting;
        const now = Date.now();

        if (!isNowIntersecting) {
          wasIntersectingRef.current = false;
          return;
        }

        // Guardrails: require activation, not already fetching, and cooldown elapsed
        if (!activated || !hasNextPage || isFetchingNextPage) return;
        if (now - lastLoadAtRef.current < cooldownMs) return;

        // If requiring a user gesture, ensure we saw one since last load
        if (requireUserScroll && !userGestureSinceLastLoadRef.current) return;

        // Trigger load
        lastLoadAtRef.current = now;
        userGestureSinceLastLoadRef.current = false;
        wasIntersectingRef.current = true;
        fetchNextPage();
      },
      {
        root: rootEl as Element | null,
        rootMargin,
        threshold,
      }
    );

    observerRef.current.observe(targetElement);

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [targetElement, rootEl, hasNextPage, isFetchingNextPage, fetchNextPage, rootMargin, threshold, activated, requireUserScroll, cooldownMs]);

  return { setTargetElement };
}
