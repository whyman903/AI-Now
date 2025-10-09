import { useEffect, useRef, useState } from "react";
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
import type { ContentItem } from "@shared/schema";

interface MosaicContentItem extends ContentItem {
  metadata?: Record<string, any> | null;
  thumbnailUrl?: string | null;
  sourceUrl?: string | null;
}

interface MosaicFeedProps {
  items: MosaicContentItem[];
  cardSize?: number;
}

const BASE_ROW_PX = 320;
const BASE_IMAGE_HEIGHT = 160;
const GRID_GAP_PX = 16;

export default function MosaicFeed({ items, cardSize = 1 }: MosaicFeedProps) {
  if (!items || items.length === 0) {
    return <div className="text-center p-8">No items to display.</div>;
  }

  const papers = items
    .filter((item) => item.metadata?.source_name === "Hugging Face Papers")
    .sort((a, b) => (a.metadata?.rank ?? 999) - (b.metadata?.rank ?? 999));

  const latestScrapeDate: string | null = papers.reduce<string | null>((latest, paper) => {
    const scrapeDate = paper.metadata?.scraped_date;
    if (!scrapeDate) return latest;
    return !latest || scrapeDate > latest ? scrapeDate : latest;
  }, null);

  // Get only the latest AI Trends summary
  const aiTrendsSummaries = items.filter(
    (item) => item.metadata?.source_name === "Tavily AI Trends"
  );
  const latestAiTrends = aiTrendsSummaries.length > 0
    ? aiTrendsSummaries.reduce((latest, current) =>
        (current.publishedAt ?? "") > (latest.publishedAt ?? "") ? current : latest
      )
    : null;

  const regularContent = items.filter(
    (item) => item.metadata?.source_name !== "Hugging Face Papers"
  );

  // Remove old AI Trends summaries, keep only the latest
  const contentWithLatestTrends = regularContent.filter(
    (item) => item.metadata?.source_name !== "Tavily AI Trends"
  );
    const finalContent = latestAiTrends 
    ? [latestAiTrends, ...contentWithLatestTrends]
    : contentWithLatestTrends;

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
          />
        </div>
      );
    });

  return (
    <div className="p-2 sm:p-3 lg:p-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
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
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 h-full"
              style={{ gridAutoRows: `${rowPx}px` }}
            >
              {renderGridItems(finalContent.slice(0, sidebarRows * 3), 0)}
            </div>
          </div>
        )}

        {papers.length > 0 && (
          <aside ref={sidebarRef} className="col-span-1 lg:col-start-4 lg:col-span-1">
            <div className="pb-3 mb-4">
              <h2 className="text-3xl font-bold text-blue-900 dark:text-gray-300">Trending Research</h2>
              {latestScrapeDate && (
                <p className="text-xs text-blue-600/80 dark:text-blue-400/70 mt-1">
                  Updated {new Date(latestScrapeDate).toLocaleDateString()}
                </p>
                
              )}
            </div>

            <div className="space-y-3">
              {papers.slice(0, 10).map((paper, idx) => (
                <div
                  key={paper.id}
                  className="trending-paper-card group cursor-pointer rounded-xl p-3 h-24 overflow-hidden bg-gradient-to-br from-blue-50 via-sky-50/50 to-background dark:bg-none dark:bg-blue-950/20 hover:shadow-[0_8px_20px_rgba(153,153,153,0.25)] transition-all duration-300 border-l-4 border-blue-500 dark:border-blue-700"
                  onClick={() => paper.sourceUrl && window.open(paper.sourceUrl, "_blank")}
                >
                  <div className="flex items-start gap-3">
                    <div className="shrink-0 mt-0.5">
                      <span className="text-2xl font-bold text-blue-600 dark:text-gray-300 font-mono">
                        {idx + 1}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className={`trending-paper-title font-serif ${paper.title.length > 100 ? "text-xs" : "text-sm"} font-semibold leading-snug line-clamp-2 text-blue-900 dark:text-gray-300`}>
                          {paper.title}
                        </h3>
                        {paper.metadata?.github_url && (
                          <button
                            type="button"
                            aria-label="Open associated GitHub repository"
                            className="trending-paper-github-btn shrink-0 inline-flex items-center justify-center rounded-md border border-transparent p-1 transition-colors bg-blue-200/60 hover:bg-blue-200 dark:bg-blue-900/50 dark:hover:bg-blue-800/60"
                            onClick={(event) => {
                              event.stopPropagation();
                              window.open(paper.metadata?.github_url, "_blank", "noopener,noreferrer");
                            }}
                          >
                            <Github className="h-4 w-4 text-blue-700 dark:text-gray-300" />
                          </button>
                        )}
                      </div>
                      {paper.author && (
                        <p className="text-xs text-blue-600/80 dark:text-blue-400/80 mt-1 truncate">By {paper.author}</p>
                      )}
                    </div>
                  </div>
                </div>
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
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
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
}

function ArticleCard({ item, imageHeight, variant = "default" }: ArticleCardProps) {
  const hasThumbnail = !!item.thumbnailUrl;
  const [hideImage, setHideImage] = useState(!hasThumbnail);
  const githubUrl = item.metadata?.github_url as string | undefined;
  const isAiTrends = item.metadata?.source_name === "Tavily AI Trends";
  const [showYouTubePlayer, setShowYouTubePlayer] = useState(false);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);

  const getCardStyleClasses = () => {
    if (isAiTrends) {
      return "relative overflow-hidden bg-gradient-to-br from-cyan-50 via-blue-50/50 to-background dark:from-emerald-950/30 dark:via-teal-950/20 dark:to-background hover:shadow-xl transition-all duration-300 border-l-4 border-cyan-500 dark:border-emerald-600";
    }
    switch (item.type) {
      case "youtube_video":
        return "article-card-youtube";
      default:
        return "article-card-default";
    }
  };

  const getIcon = () => {
    if (isAiTrends) {
      return <TrendingUp className="h-4 w-4 text-cyan-600 dark:text-gray-300" />;
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
  };

  const handleCardClick = () => {
    if (item.sourceUrl) {
      window.open(item.sourceUrl, "_blank");
    }
  };

  const isYouTube = item.type === "youtube_video";
  
  // Extract YouTube video ID from URL
  const getYouTubeVideoId = (url: string): string | null => {
    const patterns = [
      /(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/,
      /youtube\.com\/embed\/([^&\n?#]+)/,
    ];
    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) return match[1];
    }
    return null;
  };

  const youtubeVideoId = isYouTube && item.sourceUrl ? getYouTubeVideoId(item.sourceUrl) : null;

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
  let titleSize = isAiTrends ? "text-xl" : "text-lg"; // Bigger title for AI Trends

  const longTitleRules = [
    { minLength: 220, size: "text-xs" },
    { minLength: 170, size: "text-sm" },
    { minLength: 130, size: "text-base" },
  ];

  // Don't apply long title rules to AI Trends
  if (!isAiTrends) {
    for (const rule of longTitleRules) {
      if (titleLength >= rule.minLength) {
        titleSize = rule.size;
        break;
      }
    }

    if (titleLength >= 170 && hideImage) {
      titleClamp = "line-clamp-2";
    }
  }

  const containerPadding = variant === "featured" ? "lg:p-6" : "";
  const featuredTitleBoost = variant === "featured" && titleLength < 160 && !isAiTrends;
  if (featuredTitleBoost) {
    titleSize = "text-2xl";
    if (!hideImage) {
      titleClamp = "line-clamp-3";
    }
  }

  const titleMargin = titleLength >= 170 ? "mb-1" : titleLength >= 120 ? "mb-2" : "mb-3";

  return (
    <div
      className={`group cursor-pointer flex flex-col p-4 ${containerPadding} rounded-2xl w-full h-full overflow-hidden ${getCardStyleClasses()}`}
      onClick={handleCardClick}
    >
      {/* Subtle accent for AI Trends */}
      {isAiTrends && (
        <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-400/20 dark:bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />
      )}

      {!hideImage && (
        <div
          className="overflow-hidden rounded-xl w-full flex items-center justify-center relative"
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

      <div className={`flex flex-col justify-start flex-grow overflow-hidden relative ${!hideImage ? "pt-3" : ""}`} style={{ zIndex: 1 }}>
        <div>
          {!isAiTrends && (
            <div className="flex items-center justify-between text-sm text-muted-foreground mb-2">
              <div className="flex items-center">
                {getIcon()}
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
              ? "text-cyan-900 dark:text-gray-300 group-hover:text-cyan-700 dark:group-hover:text-gray-300" 
              : "group-hover:text-primary"
          }`}>
            {isAiTrends ? "What's Happening Now?" : item.title}
          </h3>

          {/* Only show summary for AI Trends digest */}
          {isAiTrends && item.metadata?.summary && (
            <div className={`text-foreground dark:text-gray-300 ${summaryClamp} leading-relaxed prose max-w-none`}>
              <ReactMarkdown
                components={{
                  a: ({ node, ...props }) => (
                    <a
                      {...props}
                      className="text-cyan-600 dark:text-gray-300 hover:text-cyan-700 dark:hover:text-gray-400 underline transition-colors"
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ),
                  ol: ({ node, ...props }) => (
                    <ol {...props} className="space-y-4 list-decimal pl-6 marker:font-semibold marker:text-cyan-600 dark:marker:text-gray-300" />
                  ),
                  ul: ({ node, ...props }) => (
                    <ul {...props} className="space-y-2 list-disc pl-5" />
                  ),
                  li: ({ node, ...props }) => (
                    <li {...props} className="text-base leading-relaxed" />
                  ),
                  p: ({ node, ...props }) => (
                    <p {...props} className="text-base leading-relaxed" />
                  ),
                  strong: ({ node, ...props }) => (
                    <strong {...props} className="font-semibold text-cyan-900 dark:text-gray-300" />
                  ),
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
}

