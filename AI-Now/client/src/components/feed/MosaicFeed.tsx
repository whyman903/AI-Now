import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, RefCallback } from "react";
import { Badge } from "@/components/ui/badge";
import {
  FileText,
  Mic,
  PlaySquare,
  X,
  FlaskConical,
  TrendingUp,
  ChevronRight,
  Github,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import ReactMarkdown from "react-markdown";
import { trackContentClick, trackContentView } from "@/lib/analytics";
import { useViewTracking } from "@/hooks/use-view-tracking";
import type { ContentItem } from "@shared/schema";

interface MosaicContentItem extends ContentItem {
  metadata?: Record<string, any> | null;
  thumbnailUrl?: string | null;
  sourceUrl?: string | null;
}

interface MosaicFeedProps {
  items: MosaicContentItem[];
  cardSize?: number;
  isFiltering?: boolean;
}

const BASE_ROW_PX = 288;
const BASE_IMAGE_HEIGHT = 144;
const GRID_GAP_PX = 14;
const MAX_ANALYTICS_STRING_LENGTH = 200;
const MAX_ANALYTICS_ARRAY_LENGTH = 10;
const METADATA_DENYLIST = new Set([
  "summary",
  "content",
  "body",
  "raw",
  "raw_html",
  "raw_text",
  "chunks",
  "source_documents",
  "sections",
]);

function sanitizeAnalyticsMetadata(
  metadata: Record<string, any> | null | undefined
): Record<string, unknown> | undefined {
  if (!metadata) {
    return undefined;
  }

  const sanitized: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(metadata)) {
    if (value == null || METADATA_DENYLIST.has(key)) {
      continue;
    }

    if (typeof value === "string") {
      const trimmed = value.trim();
      if (!trimmed) {
        continue;
      }
      sanitized[key] =
        trimmed.length > MAX_ANALYTICS_STRING_LENGTH
          ? `${trimmed.slice(0, MAX_ANALYTICS_STRING_LENGTH)}…`
          : trimmed;
      continue;
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        continue;
      }
      sanitized[key] = value.slice(0, MAX_ANALYTICS_ARRAY_LENGTH);
      continue;
    }

    if (typeof value === "object") {
      // Nested objects can be large; skip them for analytics payloads.
      continue;
    }

    sanitized[key] = value;
  }

  return Object.keys(sanitized).length > 0 ? sanitized : undefined;
}

const seenContentViews = new Set<string>();

const LONG_TITLE_RULES = [
  { minLength: 220, size: "text-[0.7rem]" },
  { minLength: 170, size: "text-xs" },
  { minLength: 130, size: "text-sm" },
] as const;

const YOUTUBE_URL_PATTERNS = [
  /(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/,
  /youtube\.com\/embed\/([^&\n?#]+)/,
] as const;

interface TrendingPaperCardProps {
  paper: MosaicContentItem;
  index: number;
  isFiltering: boolean;
}

interface TrendingPaperTrackingSnapshot {
  id: string;
  index: number;
  type: string;
  metadata: Record<string, any> | null | undefined;
  sourceUrl: string | null | undefined;
}

function extractYouTubeVideoId(url: string): string | null {
  for (const pattern of YOUTUBE_URL_PATTERNS) {
    const match = url.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return null;
}

function getCardStyleClasses(isAiTrends: boolean, type: string): string {
  if (isAiTrends) {
    return "article-card-ai-trends overflow-hidden";
  }

  switch (type) {
    case "youtube_video":
      return "article-card-youtube";
    case "podcast":
      return "article-card-podcast";
    default:
      return "article-card-default";
  }
}

function renderItemIcon(item: MosaicContentItem, isAiTrends: boolean): JSX.Element {
  if (isAiTrends) {
    return <TrendingUp className="h-4 w-4 text-slate-500 dark:text-gray-300" />;
  }

  if (item.metadata?.source_name === "Hugging Face Papers") {
    return <FlaskConical className="h-4 w-4" />;
  }

  switch (item.type) {
    case "youtube_video":
      return <PlaySquare className="h-4 w-4" />;
    case "podcast":
      return <Mic className="h-4 w-4" />;
    case "research_paper":
    case "academic":
      return <FileText className="h-4 w-4" />;
    case "twitter_post":
      return <X className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
}

const TrendingPaperCard = memo(function TrendingPaperCard({ paper, index, isFiltering }: TrendingPaperCardProps) {
  const snapshotRef = useRef<TrendingPaperTrackingSnapshot>({
    id: paper.id,
    index,
    type: paper.type,
    metadata: paper.metadata,
    sourceUrl: paper.sourceUrl,
  });

  useEffect(() => {
    snapshotRef.current = {
      id: paper.id,
      index,
      type: paper.type,
      metadata: paper.metadata,
      sourceUrl: paper.sourceUrl,
    };
  }, [index, paper.id, paper.metadata, paper.sourceUrl, paper.type]);

  const handleView = useCallback(() => {
    const snapshot = snapshotRef.current;
    if (seenContentViews.has(snapshot.id)) {
      return;
    }

    seenContentViews.add(snapshot.id);
    trackContentView(snapshot.id, {
      position: snapshot.index,
      sourceName: snapshot.metadata?.source_name ?? undefined,
      contentType: snapshot.type,
      metadata: sanitizeAnalyticsMetadata(snapshot.metadata),
    });
  }, []);

  const registerViewRef = useViewTracking(handleView, { enabled: !isFiltering });

  const handleClick = useCallback(() => {
    const snapshot = snapshotRef.current;
    if (!snapshot.sourceUrl) {
      return;
    }

    trackContentClick(snapshot.id, {
      position: snapshot.index,
      sourceName: snapshot.metadata?.source_name ?? undefined,
      contentType: snapshot.type,
      metadata: sanitizeAnalyticsMetadata(snapshot.metadata),
    });

    window.open(snapshot.sourceUrl, "_blank", "noopener,noreferrer");
  }, []);

  const handleGithubClick = useCallback((event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    const snapshot = snapshotRef.current;
    const githubUrl = snapshot.metadata?.github_url as string | undefined;
    if (githubUrl) {
      window.open(githubUrl, "_blank", "noopener,noreferrer");
    }
  }, []);

  return (
    <div
      ref={registerViewRef as RefCallback<HTMLDivElement>}
      className="trending-paper-card group cursor-pointer rounded-xl p-2.5 h-20 overflow-hidden bg-gradient-to-br from-blue-50 via-sky-50/50 to-background dark:bg-none dark:bg-blue-950/20 hover:shadow-[0_8px_20px_rgba(153,153,153,0.25)] transition-all duration-300 border-l-4 border-blue-500 dark:border-blue-700"
      onClick={handleClick}
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5">
          <span className="text-xl font-bold text-blue-600 dark:text-gray-300 font-mono">
            {index + 1}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3
              className={`trending-paper-title font-serif ${
                paper.title.length > 100 ? "text-[0.7rem]" : "text-xs"
              } font-semibold leading-snug line-clamp-2 text-blue-900 dark:text-gray-300`}
            >
              {paper.title}
            </h3>
            {paper.metadata?.github_url && (
              <button
                type="button"
                aria-label="Open associated GitHub repository"
                className="trending-paper-github-btn shrink-0 inline-flex items-center justify-center rounded-md border border-transparent p-1 transition-colors bg-blue-200/60 hover:bg-blue-200 dark:bg-blue-900/50 dark:hover:bg-blue-800/60"
                onClick={handleGithubClick}
              >
                <Github className="h-3.5 w-3.5 text-blue-700 dark:text-gray-300" />
              </button>
            )}
          </div>
          {paper.author && (
            <p className="text-[0.7rem] text-gray-600 dark:text-gray-400 mt-1 truncate">By {paper.author}</p>
          )}
        </div>
      </div>
    </div>
  );
});

export default function MosaicFeed({ items, cardSize = 1, isFiltering = false }: MosaicFeedProps) {
  if (!items || items.length === 0) {
    return <div className="text-center p-8">No items to display.</div>;
  }

  const { papers, latestScrapeDate, finalContent } = useMemo(() => {
    const huggingFacePapers: MosaicContentItem[] = [];
    const regularContent: MosaicContentItem[] = [];
    const aiTrendsSummaries: MosaicContentItem[] = [];

    for (const item of items) {
      const sourceName = item.metadata?.source_name;
      if (sourceName === "Hugging Face Papers") {
        huggingFacePapers.push(item);
        continue;
      }

      if (sourceName === "Tavily AI Trends") {
        aiTrendsSummaries.push(item);
        continue;
      }

      regularContent.push(item);
    }

    const sortedPapers = [...huggingFacePapers].sort(
      (a, b) => (a.metadata?.rank ?? 999) - (b.metadata?.rank ?? 999)
    );

    const derivedLatestScrapeDate = sortedPapers.reduce<string | null>((latest, paper) => {
      const scrapeDate = paper.metadata?.scraped_date;
      if (!scrapeDate) return latest;
      return !latest || scrapeDate > latest ? scrapeDate : latest;
    }, null);

    let latestAiTrends: MosaicContentItem | null = null;
    let latestAiTrendsTimestamp = Number.NEGATIVE_INFINITY;

    for (const summary of aiTrendsSummaries) {
      const publishedAt = summary.publishedAt ? new Date(summary.publishedAt).getTime() : NaN;
      const parsed = Number.isNaN(publishedAt) ? Number.NEGATIVE_INFINITY : publishedAt;
      if (parsed > latestAiTrendsTimestamp) {
        latestAiTrends = summary;
        latestAiTrendsTimestamp = parsed;
      }
    }

    const combinedContent = latestAiTrends
      ? [latestAiTrends, ...regularContent]
      : [...regularContent];

    return {
      papers: sortedPapers,
      latestScrapeDate: derivedLatestScrapeDate,
      finalContent: combinedContent,
    };
  }, [items]);

  const sidebarRef = useRef<HTMLDivElement | null>(null);
  const [sidebarRows, setSidebarRows] = useState<number>(0);
  const rowPx = Math.max(200, Math.round(BASE_ROW_PX * cardSize));
  const imageHeight = Math.max(120, Math.round(BASE_IMAGE_HEIGHT * cardSize));
  const [isLg, setIsLg] = useState<boolean>(() =>
    typeof window !== "undefined"
      ? window.matchMedia("(min-width: 1024px)").matches
      : false
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 1024px)");
    const handleChange = () => setIsLg(mq.matches);
    mq.addEventListener("change", handleChange);
    return () => mq.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    const gap = GRID_GAP_PX;
    const calc = () => {
      const el = sidebarRef.current;
      if (!el) return;
      const h = el.getBoundingClientRect().height;
      const rows = Math.max(1, Math.ceil((h + gap) / (rowPx + gap)));
      setSidebarRows(rows);
    };

    calc();
    const el = sidebarRef.current;
    const ro = el ? new ResizeObserver(calc) : null;
    if (el && ro) ro.observe(el);
    if (typeof window !== "undefined") {
      window.addEventListener("resize", calc);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("resize", calc);
      }
      ro?.disconnect();
    };
  }, [papers.length, rowPx]);

  const renderGridItems = (content: MosaicContentItem[], startIndex: number) =>
    content.map((item, index) => {
      const absoluteIndex = startIndex + index;
      const isAiTrendsTile = item.metadata?.source_name === "Tavily AI Trends";
      const isFeatured = isLg && absoluteIndex === 0 && isAiTrendsTile;
      const sizeClasses = isFeatured ? " lg:col-span-2 lg:row-span-2" : "";
      const cardHeight = isFeatured ? imageHeight * 2 + GRID_GAP_PX : imageHeight;

      return (
        <div key={item.id} className={`col-span-1 row-span-1 h-full${sizeClasses}`}>
          <ArticleCard
            item={item}
            imageHeight={cardHeight}
            variant={isFeatured ? "featured" : "default"}
            position={absoluteIndex}
            isFiltering={isFiltering}
          />
        </div>
      );
    });

  return (
    <div className="p-1.5 sm:p-2.5 lg:p-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-start">
        {isLg && (
          <div
            className="col-span-1 sm:col-span-2 lg:col-span-3 overflow-hidden"
            style={{
              height:
                sidebarRows > 0
                  ? sidebarRows * (rowPx + GRID_GAP_PX) - GRID_GAP_PX
                  : "auto",
            }}
          >
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 h-full"
            style={{ gridAutoRows: `${rowPx}px` }}
          >
            {renderGridItems(finalContent.slice(0, sidebarRows * 3), 0)}
          </div>
          </div>
        )}

        {papers.length > 0 && (
          <aside ref={sidebarRef} className="col-span-1 lg:col-start-4 lg:col-span-1">
            <div className="pb-3 mb-4">
              <h2 className="text-xl font-bold text-black dark:text-gray-300">Trending Research</h2>
              {latestScrapeDate && (
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  Updated {new Date(latestScrapeDate).toLocaleDateString()}
                </p>
                
              )}
            </div>

            <div className="space-y-2.5">
              {papers.slice(0, 10).map((paper, idx) => (
                <TrendingPaperCard
                  key={paper.id}
                  paper={paper}
                  index={idx}
                  isFiltering={isFiltering}
                />
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-blue-200 dark:border-blue-800/50">
              <a
                href="https://huggingface.co/papers/trending"
                target="_blank"
                rel="noopener noreferrer"
                className="trending-papers-link text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline flex items-center gap-1 transition-colors"
              >
                View all papers
                <ChevronRight className="h-3 w-3" />
              </a>
            </div>
          </aside>
        )}

        <div className="col-span-1 sm:col-span-2 lg:col-span-4">
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
            style={{ gridAutoRows: `${rowPx}px` }}
          >
            {renderGridItems(
              isLg ? finalContent.slice(sidebarRows * 3) : finalContent,
              isLg ? sidebarRows * 3 : 0
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ArticleCardProps {
  item: MosaicContentItem;
  imageHeight: number;
  variant?: "default" | "featured";
  position?: number;
  isFiltering: boolean;
}

interface ArticleTrackingSnapshot {
  id: string;
  position: number | undefined;
  type: string;
  metadata: Record<string, any> | null | undefined;
  sourceUrl: string | null | undefined;
}

const ArticleCard = memo(function ArticleCard({
  item,
  imageHeight,
  variant = "default",
  position,
  isFiltering,
}: ArticleCardProps) {
  const hasThumbnail = !!item.thumbnailUrl;
  const [hideImage, setHideImage] = useState(!hasThumbnail);
  const githubUrl = item.metadata?.github_url as string | undefined;
  const isAiTrends = item.metadata?.source_name === "Tavily AI Trends";
  const [showYouTubePlayer, setShowYouTubePlayer] = useState(false);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);
  const trackingSnapshotRef = useRef<ArticleTrackingSnapshot>({
    id: item.id,
    position,
    type: item.type,
    metadata: item.metadata,
    sourceUrl: item.sourceUrl,
  });

  useEffect(() => {
    trackingSnapshotRef.current = {
      id: item.id,
      position,
      type: item.type,
      metadata: item.metadata,
      sourceUrl: item.sourceUrl,
    };
  }, [item.id, item.metadata, item.sourceUrl, item.type, position]);

  const handleView = useCallback(() => {
    const snapshot = trackingSnapshotRef.current;
    if (seenContentViews.has(snapshot.id)) {
      return;
    }

    seenContentViews.add(snapshot.id);
    trackContentView(snapshot.id, {
      position: snapshot.position,
      sourceName: snapshot.metadata?.source_name ?? undefined,
      contentType: snapshot.type,
      metadata: sanitizeAnalyticsMetadata(snapshot.metadata),
    });
  }, []);

  const registerViewRef = useViewTracking(handleView, { enabled: !isFiltering });
  const cardStyleClasses = getCardStyleClasses(isAiTrends, item.type);
  const itemIcon = renderItemIcon(item, isAiTrends);

  const handleCardClick = useCallback(() => {
    const snapshot = trackingSnapshotRef.current;
    if (!snapshot.sourceUrl) {
      return;
    }

    trackContentClick(snapshot.id, {
      position: snapshot.position,
      sourceName: snapshot.metadata?.source_name ?? undefined,
      contentType: snapshot.type,
      metadata: sanitizeAnalyticsMetadata(snapshot.metadata),
    });

    window.open(snapshot.sourceUrl, "_blank", "noopener,noreferrer");
  }, []);

  const isYouTube = item.type === "youtube_video";
  const youtubeVideoId = isYouTube && item.sourceUrl ? extractYouTubeVideoId(item.sourceUrl) : null;

  // Handle hover for YouTube videos
  const handleMouseEnter = () => {
    if (isYouTube && youtubeVideoId) {
      hoverTimerRef.current = setTimeout(() => {
        setShowYouTubePlayer(true);
      }, 1000);
    }
  };

  const handleMouseLeave = () => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setShowYouTubePlayer(false);
  };

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) {
        clearTimeout(hoverTimerRef.current);
      }
    };
  }, []);

  const baseTitleClamp = hideImage ? "line-clamp-3" : "line-clamp-2";
  let titleClamp = baseTitleClamp;
  
  // AI Trends should show full summary without truncation
  let summaryClamp = hideImage
    ? "line-clamp-3"
    : variant === "featured"
    ? "line-clamp-4"
    : "line-clamp-2";
  
  if (isAiTrends) {
    summaryClamp = ""; // Show full text for AI Trends (no clamp)
    titleClamp = ""; // Don't clamp AI Trends title either
  }
  
  const titleLength = item.title.trim().length;
  let titleSize = isAiTrends ? "text-xl" : "text-base"; // Bigger title for AI Trends

  // Don't apply long title rules to AI Trends
  if (!isAiTrends) {
    for (const rule of LONG_TITLE_RULES) {
      if (titleLength >= rule.minLength) {
        titleSize = rule.size;
        break;
      }
    }

    if (titleLength >= 170 && hideImage) {
      titleClamp = "line-clamp-2";
    }
  }

  const containerPadding = variant === "featured" ? "lg:p-5" : "";
  const featuredTitleBoost = variant === "featured" && titleLength < 160 && !isAiTrends;
  if (featuredTitleBoost) {
    titleSize = "text-xl";
    if (!hideImage) {
      titleClamp = "line-clamp-3";
    }
  }

  const titleMargin = titleLength >= 170 ? "mb-1" : titleLength >= 120 ? "mb-2" : "mb-3";

  return (
    <div
      ref={registerViewRef as RefCallback<HTMLDivElement>}
      className={`group cursor-pointer flex flex-col p-3 ${containerPadding} rounded-2xl w-full h-full ${cardStyleClasses}`}
      onClick={handleCardClick}
    >
      {/* Subtle accent for AI Trends */}
      {isAiTrends && (
        <div className="ai-trends-accent" />
      )}

      {!hideImage && (
        <div
          className="overflow-hidden rounded-lg w-full flex items-center justify-center relative"
          style={{ height: `${imageHeight}px`, zIndex: 1 }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {showYouTubePlayer && youtubeVideoId ? (
            <iframe
              src={`https://www.youtube.com/embed/${youtubeVideoId}?autoplay=1&mute=1&controls=1&modestbranding=1&rel=0`}
              title={item.title}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              className="w-full h-full"
              style={{ border: 'none' }}
            />
          ) : (
            <img
              src={item.thumbnailUrl ?? undefined}
              alt={item.title}
              loading="lazy"
              decoding="async"
              sizes="(min-width: 1024px) 25vw, (min-width: 768px) 33vw, 100vw"
              className="max-w-full max-h-full object-contain group-hover:scale-105 transition-transform duration-300"
              onError={() => setHideImage(true)}
            />
          )}
        </div>
      )}

      <div className={`flex flex-col justify-start flex-grow overflow-hidden relative ${!hideImage ? "pt-2.5" : ""}`} style={{ zIndex: 1 }}>
        <div>
          {!isAiTrends && (
            <div className="flex items-center justify-between text-sm text-muted-foreground mb-1.5">
              <div className="flex items-center">
                {itemIcon}
                <span className="ml-2 capitalize">{item.type.replace("_", " ")}</span>
              </div>
              <div className="flex items-center gap-2">
                {githubUrl && (
                  <button
                    type="button"
                    aria-label="Open associated GitHub repository"
                    className="inline-flex items-center justify-center rounded-md border border-transparent bg-muted text-foreground hover:bg-muted/80 transition-colors p-1"
                    onClick={(event) => {
                      event.stopPropagation();
                      window.open(githubUrl, "_blank", "noopener,noreferrer");
                    }}
                  >
                    <Github className="h-4 w-4" />
                  </button>
                )}
                {item.metadata?.source_name === "Hugging Face Papers" && (
                  <Badge variant="outline" className="text-xs px-2 py-0 h-5 flex items-center gap-1">
                    <TrendingUp className="h-3 w-3" />
                    Trending
                  </Badge>
                )}
              </div>
            </div>
          )}

          <h3 className={`font-serif font-bold ${titleSize} ${titleMargin} leading-tight transition-colors ${titleClamp} ${
            isAiTrends 
              ? "text-black dark:text-gray-300 group-hover:text-black dark:group-hover:text-gray-300" 
              : "group-hover:text-primary"
          }`}>
            {isAiTrends ? "What's Happening Now?" : item.title}
          </h3>

          {/* Only show summary for AI Trends digest */}
          {isAiTrends && item.metadata?.summary && (
            <div className={`ai-trends-prose ${summaryClamp} leading-relaxed`}>
              <ReactMarkdown
                components={{
                  a: ({ node, ...props }) => (
                    <a
                      {...props}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ),
                  ol: ({ node, ...props }) => <ol {...props} />,
                  ul: ({ node, ...props }) => <ul {...props} />,
                  li: ({ node, ...props }) => <li {...props} />,
                  p: ({ node, ...props }) => <p {...props} />,
                  strong: ({ node, ...props }) => <strong {...props} />,
                }}
              >
                {item.metadata.summary.replace(/\\n/g, '\n')}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {!isAiTrends && (
          <div className="flex items-center justify-between text-sm text-muted-foreground mt-auto pt-2 min-h-[2.25rem]">
            <div className="font-medium truncate">{item.author || "Unknown"}</div>
            {item.publishedAt && (
              <div className="shrink-0 ml-2">
                {formatDistanceToNow(new Date(item.publishedAt), {
                  addSuffix: true,
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});
