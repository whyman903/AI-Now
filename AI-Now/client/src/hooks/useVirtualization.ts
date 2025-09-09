import { useState, useEffect, useRef, useCallback } from 'react';

interface VirtualizationOptions {
  itemCount: number;
  estimatedItemHeight: number;
  overscan?: number;
  getItemHeight?: (index: number) => number;
}

interface VirtualizationResult {
  virtualItems: Array<{
    index: number;
    start: number;
    size: number;
  }>;
  totalSize: number;
  scrollToIndex: (index: number) => void;
  containerRef: React.RefObject<HTMLDivElement>;
  wrapperStyle: React.CSSProperties;
}

export function useVirtualization({
  itemCount,
  estimatedItemHeight,
  overscan = 3,
  getItemHeight,
}: VirtualizationOptions): VirtualizationResult {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(0);
  const measuredHeights = useRef<Map<number, number>>(new Map());

  // Calculate which items should be visible
  const calculateVisibleRange = useCallback(() => {
    let accumulatedHeight = 0;
    let startIndex = 0;
    let endIndex = itemCount - 1;

    // Find start index
    for (let i = 0; i < itemCount; i++) {
      const height = getItemHeight?.(i) ?? measuredHeights.current.get(i) ?? estimatedItemHeight;
      if (accumulatedHeight + height > scrollTop) {
        startIndex = Math.max(0, i - overscan);
        break;
      }
      accumulatedHeight += height;
    }

    // Find end index
    accumulatedHeight = 0;
    for (let i = startIndex; i < itemCount; i++) {
      if (accumulatedHeight > scrollTop + containerHeight) {
        endIndex = Math.min(itemCount - 1, i + overscan);
        break;
      }
      const height = getItemHeight?.(i) ?? measuredHeights.current.get(i) ?? estimatedItemHeight;
      accumulatedHeight += height;
    }

    return { startIndex, endIndex };
  }, [scrollTop, containerHeight, itemCount, estimatedItemHeight, overscan, getItemHeight]);

  const { startIndex, endIndex } = calculateVisibleRange();

  // Calculate virtual items with positions
  const virtualItems = [];
  let offset = 0;

  for (let i = 0; i < itemCount; i++) {
    const height = getItemHeight?.(i) ?? measuredHeights.current.get(i) ?? estimatedItemHeight;
    
    if (i >= startIndex && i <= endIndex) {
      virtualItems.push({
        index: i,
        start: offset,
        size: height,
      });
    }
    
    offset += height;
  }

  const totalSize = offset;

  // Handle scroll events
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      setScrollTop(container.scrollTop);
    };

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setContainerHeight(entry.contentRect.height);
      }
    });

    container.addEventListener('scroll', handleScroll, { passive: true });
    resizeObserver.observe(container);

    // Initial measurements
    setScrollTop(container.scrollTop);
    setContainerHeight(container.clientHeight);

    return () => {
      container.removeEventListener('scroll', handleScroll);
      resizeObserver.disconnect();
    };
  }, []);

  // Scroll to specific index
  const scrollToIndex = useCallback((index: number) => {
    if (!containerRef.current) return;
    
    let offset = 0;
    for (let i = 0; i < index; i++) {
      offset += getItemHeight?.(i) ?? measuredHeights.current.get(i) ?? estimatedItemHeight;
    }
    
    containerRef.current.scrollTop = offset;
  }, [estimatedItemHeight, getItemHeight]);

  const wrapperStyle: React.CSSProperties = {
    height: totalSize,
    position: 'relative',
    width: '100%',
  };

  return {
    virtualItems,
    totalSize,
    scrollToIndex,
    containerRef,
    wrapperStyle,
  };
}