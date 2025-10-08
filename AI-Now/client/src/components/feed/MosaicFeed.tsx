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
            <div className="pb-2 mb-3">
              <h2 className="text-lg font-bold">Trending Papers</h2>
              {latestScrapeDate && (
                <p className="text-xs text-muted-foreground mt-1">
                  Updated {new Date(latestScrapeDate).toLocaleDateString()}
                </p>
              )}
            </div>

            <div className="space-y-3">
              {papers.slice(0, 10).map((paper, idx) => (
                <div
                  key={paper.id}
                  className="trending-paper-card group cursor-pointer rounded-xl border p-3 h-24 overflow-hidden"
                  onClick={() => paper.sourceUrl && window.open(paper.sourceUrl, "_blank")}
                >
                  <div className="flex items-start gap-3">
                    <div className="shrink-0 mt-0.5">
                      <span className="trending-paper-rank-badge inline-flex items-center justify-center w-6 h-6 rounded-md text-white text-xs font-mono">
                        {idx + 1}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className={`trending-paper-title font-serif ${paper.title.length > 100 ? "text-xs" : "text-sm"} font-semibold leading-snug line-clamp-2`}>
                          {paper.title}
                        </h3>
                        {paper.metadata?.github_url && (
                          <button
                            type="button"
                            aria-label="Open associated GitHub repository"
                            className="trending-paper-github-btn shrink-0 inline-flex items-center justify-center rounded-md border border-transparent p-1"
                            onClick={(event) => {
                              event.stopPropagation();
                              window.open(paper.metadata?.github_url, "_blank", "noopener,noreferrer");
                            }}
                          >
                            <Github className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                      {paper.author && (
                        <p className="text-xs text-muted-foreground mt-1 truncate">By {paper.author}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t">
              <a
                href="https://huggingface.co/papers/trending"
                target="_blank"
                rel="noopener noreferrer"
                className="trending-papers-link text-sm hover:underline flex items-center gap-1"
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

  const getCardStyleClasses = () => {
    if (isAiTrends) {
      return "relative overflow-hidden border-2 border-primary/20 bg-gradient-to-br from-primary/5 via-background to-primary/10 hover:border-primary/40 hover:shadow-lg";
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
      return <TrendingUp className="h-4 w-4 text-primary" />;
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
      {/* Decorative background for AI Trends */}
      {isAiTrends && (
        <>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl -translate-y-16 translate-x-16 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl translate-y-16 -translate-x-16 pointer-events-none" />
        </>
      )}

      {!hideImage && (
        <div
          className="overflow-hidden rounded-xl w-full flex items-center justify-center relative"
          style={{ height: `${imageHeight}px`, zIndex: 1 }}
        >
          <img
            src={item.thumbnailUrl ?? undefined}
            alt={item.title}
            loading="lazy"
            decoding="async"
            sizes="(min-width: 1024px) 25vw, (min-width: 768px) 33vw, 100vw"
            className="max-w-full max-h-full object-contain group-hover:scale-105 transition-transform duration-300"
            onError={() => setHideImage(true)}
          />
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

          <h3 className={`font-serif font-bold ${titleSize} ${titleMargin} leading-tight group-hover:text-primary transition-colors ${titleClamp}`}>
            {isAiTrends ? "What's Happening?" : item.title}
          </h3>

          {/* Only show summary for AI Trends digest */}
          {isAiTrends && item.metadata?.summary && (
            <div className={`text-foreground ${summaryClamp} leading-relaxed prose max-w-none`}>
              <ReactMarkdown
                components={{
                  a: ({ node, ...props }) => (
                    <a
                      {...props}
                      className="text-primary hover:text-primary/80 underline transition-colors"
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ),
                  ol: ({ node, ...props }) => (
                    <ol {...props} className="space-y-4 list-decimal pl-6 marker:font-semibold marker:text-primary/70" />
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
                    <strong {...props} className="font-semibold text-foreground" />
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
