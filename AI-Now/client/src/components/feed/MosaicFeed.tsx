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

  const regularContent = items.filter(
    (item) => item.metadata?.source_name !== "Hugging Face Papers"
  );

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
              {regularContent.slice(0, sidebarRows * 3).map((item) => (
                <div key={item.id} className="col-span-1 row-span-1 h-full">
                  <ArticleCard item={item} imageHeight={imageHeight} />
                </div>
              ))}
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
                  className="group cursor-pointer rounded-xl border bg-blue-700/10 border-blue-700/30 hover:border-blue-600/50 transition-colors p-3 h-24 overflow-hidden"
                  onClick={() => paper.sourceUrl && window.open(paper.sourceUrl, "_blank")}
                >
                  <div className="flex items-start gap-3">
                    <div className="shrink-0 mt-0.5">
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-blue-700 text-white text-xs font-mono">
                        {idx + 1}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-serif text-sm font-semibold leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-2">
                          {paper.title}
                        </h3>
                        {paper.metadata?.github_url && (
                          <button
                            type="button"
                            aria-label="Open associated GitHub repository"
                            className="shrink-0 inline-flex items-center justify-center rounded-md border border-transparent bg-blue-700/15 text-blue-700 hover:bg-blue-700/25 transition-colors p-1"
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
                className="text-sm text-blue-700 hover:underline flex items-center gap-1"
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
            {(isLg ? regularContent.slice(sidebarRows * 3) : regularContent).map((item) => (
              <div key={item.id} className="col-span-1 row-span-1 h-full">
                <ArticleCard item={item} imageHeight={imageHeight} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ArticleCardProps {
  item: MosaicContentItem;
  imageHeight: number;
}

function ArticleCard({ item, imageHeight }: ArticleCardProps) {
  const hasThumbnail = !!item.thumbnailUrl;
  const [hideImage, setHideImage] = useState(!hasThumbnail);
  const githubUrl = item.metadata?.github_url as string | undefined;

  const getCardStyleClasses = () => {
    switch (item.type) {
      case "youtube_video":
        return "bg-orange-50 dark:bg-orange-950/50 border-orange-200 dark:border-orange-800/50 hover:border-orange-400/50";
      default:
        return "bg-[#FAF9F5] dark:bg-[#2A2823] border-[#F0EEE8] dark:border-[#3D3930] hover:border-amber-400/50";
    }
  };

  const getIcon = () => {
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

  const titleClamp = hideImage ? "line-clamp-3" : "line-clamp-2";
  const summaryClamp = hideImage ? "line-clamp-3" : "line-clamp-2";

  return (
    <div
      className={`group cursor-pointer flex flex-col border p-4 rounded-2xl shadow-none hover:shadow-xl transition-shadow duration-300 w-full h-full overflow-hidden ${getCardStyleClasses()}`}
      onClick={handleCardClick}
    >
      {!hideImage && (
        <div
          className="overflow-hidden rounded-xl w-full flex items-center justify-center"
          style={{ height: `${imageHeight}px` }}
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

      <div className={`flex flex-col justify-start flex-grow overflow-hidden ${!hideImage ? "pt-3" : ""}`}>
        <div>
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

          <h3
            className={`font-serif font-bold text-lg mb-2 leading-tight group-hover:text-primary transition-colors ${titleClamp}`}
          >
            {item.title}
          </h3>

          {item.aiSummary && (
            <p className={`text-muted-foreground text-base ${summaryClamp} mb-3 leading-snug`}>
              {item.aiSummary}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between text-sm text-muted-foreground mt-auto pt-2">
          <div className="font-medium truncate">{item.author || "Unknown"}</div>
          {item.publishedAt && (
            <div className="shrink-0 ml-2">
              {formatDistanceToNow(new Date(item.publishedAt), {
                addSuffix: true,
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
