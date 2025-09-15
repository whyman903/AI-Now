import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { isUnauthorizedError } from "@/lib/authUtils";
import { Badge } from "@/components/ui/badge";
import { 
  FileText, 
  Mic, 
  PlaySquare, 
  X, 
  Bookmark, 
  BookmarkCheck,
  FlaskConical,
  TrendingUp,
  ChevronRight
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { ContentItem } from "@shared/schema";

interface ContentItemWithInteractions extends ContentItem {
  isBookmarked: boolean;
  userInteractions: any[];
  metadata?: any;
}

interface MosaicFeedProps {
  items: ContentItemWithInteractions[];
}

export default function MosaicFeed({ items }: MosaicFeedProps) {
  if (!items || items.length === 0) {
    return <div className="text-center p-8">No items to display.</div>;
  }

  // Separate papers from regular content
  // Prefer the API-provided research_paper list (already ordered),
  // but fall back to latest scraped_date grouping if needed.
  const apiPapers = items.filter(item => item.type === 'research_paper');
  const allPapers = items.filter(item => item.metadata?.source_name === 'Hugging Face Papers');

  const latestScrapeDate: string | null = (apiPapers.length > 0 ? apiPapers : allPapers)
    .reduce<string | null>((latest, paper) => {
      const scrapeDate = paper.metadata?.scraped_date;
      if (!scrapeDate) return latest;
      return !latest || scrapeDate > latest ? scrapeDate : latest;
    }, null);

  const papers = (apiPapers.length > 0
    ? apiPapers
    : allPapers
        .filter(paper => {
          if (!paper.metadata?.scraped_date || !latestScrapeDate) return false;
          const paperDate = paper.metadata.scraped_date.split('T')[0];
          const latestDate = latestScrapeDate.split('T')[0];
          return paperDate === latestDate;
        })
    )
    .filter(p => p.metadata?.source_name === 'Hugging Face Papers')
    .sort((a, b) => (a.metadata?.rank || 999) - (b.metadata?.rank || 999));
  
  const regularContent = items.filter(item => 
    item.metadata?.source_name !== 'Hugging Face Papers'
  );

  // Uniform checkerboard grid
  const ROW_PX = 320; // fixed tile height
  const sidebarRef = useRef<HTMLDivElement | null>(null);
  const [sidebarHeight, setSidebarHeight] = useState<number>(0);
  const [sidebarRows, setSidebarRows] = useState<number>(0);

  // simple matchMedia for lg breakpoint (Tailwind lg=1024px)
  const [isLg, setIsLg] = useState<boolean>(() => window.matchMedia('(min-width: 1024px)').matches);
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const onChange = () => setIsLg(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    const gap = 16; // Tailwind gap-4
    const calc = () => {
      const el = sidebarRef.current;
      if (!el) return;
      const h = el.getBoundingClientRect().height;
      setSidebarHeight(h);
      const rows = Math.max(1, Math.ceil((h + gap) / (ROW_PX + gap)));
      setSidebarRows(rows);
    };
    calc();
    const el = sidebarRef.current;
    const ro = el ? new ResizeObserver(calc) : null;
    if (el && ro) ro.observe(el);
    window.addEventListener('resize', calc);
    return () => {
      window.removeEventListener('resize', calc);
      ro?.disconnect();
    };
  }, [papers.length]);

  return (
    <div className="p-2 sm:p-3 lg:p-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
        {/* Top row: left chunk (3 cols) + sidebar (col 4) */}
        {isLg && (
          <div
            className="col-span-1 sm:col-span-2 lg:col-span-3 overflow-hidden"
            style={{
              height: sidebarRows > 0 ? sidebarRows * (ROW_PX + 16) - 16 : 'auto',
            }}
          >
            <div
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 h-full"
              style={{ gridAutoRows: `${ROW_PX}px` }}
            >
              {regularContent.slice(0, sidebarRows * 3).map((item) => (
                <div key={item.id} className="col-span-1 row-span-1 h-full">
                  <ArticleCard item={item} layout="regular" />
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
                  onClick={() => window.open(paper.sourceUrl, '_blank')}
                >
                  <div className="flex items-start gap-3">
                    <div className="shrink-0 mt-0.5">
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-blue-700 text-white text-xs font-mono">
                        {idx + 1}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-serif text-sm font-semibold leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-2">
                        {paper.title}
                      </h3>
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

        {/* Remainder: full 4-column grid below */}
        <div className="col-span-1 sm:col-span-2 lg:col-span-4">
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
            style={{ gridAutoRows: `${ROW_PX}px` }}
          >
            {(isLg ? regularContent.slice(sidebarRows * 3) : regularContent).map((item) => (
              <div key={item.id} className="col-span-1 row-span-1 h-full">
                <ArticleCard item={item} layout="regular" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ArticleCardProps {
  item: ContentItemWithInteractions;
  layout: 'hero' | 'regular' | 'wide';
}

function ArticleCard({ item, layout }: ArticleCardProps) {
  const [isBookmarked, setIsBookmarked] = useState(item.isBookmarked);
  const { toast } = useToast();

  const getCardStyleClasses = () => {
    switch (item.type) {
      case 'youtube_video':
        return 'bg-orange-50 dark:bg-orange-950/50 border-orange-200 dark:border-orange-800/50 hover:border-orange-400/50';
      default:
        return 'bg-sky-50 dark:bg-sky-950/50 border-sky-200 dark:border-sky-800/50 hover:border-sky-400/50';
    }
  };

  const getIcon = () => {
    if (item.metadata?.source_name === 'Hugging Face Papers') {
      return <FlaskConical className="h-4 w-4" />;
    }
    
    switch (item.type) {
      case 'youtube_video': return <PlaySquare className="h-4 w-4" />;
      case 'podcast': return <Mic className="h-4 w-4" />;
      case 'research_paper': 
      case 'academic': return <FileText className="h-4 w-4" />;
      case 'twitter_post': return <X className="h-4 w-4" />;
      default: return <FileText className="h-4 w-4" />;
    }
  };

  const bookmarkMutation = useMutation({
    mutationFn: async (contentItemId: string) => {
      if (isBookmarked) {
        return apiRequest("DELETE", `/api/bookmarks/${contentItemId}`);
      } else {
        return apiRequest("POST", "/api/bookmarks", { contentItemId });
      }
    },
    onSuccess: () => {
      setIsBookmarked(!isBookmarked);
      queryClient.invalidateQueries({ queryKey: ["/api/content"] });
      queryClient.invalidateQueries({ queryKey: ["/api/bookmarks"] });
      toast({
        title: isBookmarked ? "Bookmark removed" : "Bookmarked",
      });
    },
    onError: (error: any) => {
      if (isUnauthorizedError(error)) {
        window.location.href = "/login";
      } else {
        toast({
          title: "Error",
          description: "Failed to update bookmark",
          variant: "destructive",
        });
      }
    },
  });

  const handleBookmarkClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    bookmarkMutation.mutate(item.id);
  };

  const handleCardClick = () => {
    if (item.sourceUrl) {
      window.open(item.sourceUrl, '_blank');
    }
  };
  
  const hasThumbnail = !!item.thumbnailUrl;
  const [hideImage, setHideImage] = useState(!hasThumbnail);

  const layoutConfig = {
    hero: {
      flexDirection: "flex-col",
      imageContainer: "w-full h-40",
      contentContainer: !hideImage ? "pt-3" : "",
      titleSize: "text-lg",
      summaryClamp: "line-clamp-2",
      minHeight: "h-full",
    },
    wide: {
      flexDirection: "flex-col",
      imageContainer: "w-full h-40",
      contentContainer: !hideImage ? "pt-3" : "",
      titleSize: "text-lg",
      summaryClamp: "line-clamp-2",
      minHeight: "h-full",
    },
    regular: {
      flexDirection: "flex-col",
      imageContainer: "w-full h-40",
      contentContainer: !hideImage ? "pt-3" : "",
      titleSize: "text-lg",
      summaryClamp: "line-clamp-2",
      minHeight: "h-full",
    },
  };

  const currentLayout = layoutConfig[layout];
  const titleClamp = hideImage ? 'line-clamp-3' : 'line-clamp-2';
  const summaryClamp = hideImage ? 'line-clamp-3' : currentLayout.summaryClamp;

  return (
    <div
      className={`group cursor-pointer flex ${currentLayout.flexDirection} border p-4 rounded-2xl shadow-none hover:shadow-md transition-shadow duration-300 w-full h-full overflow-hidden ${getCardStyleClasses()}`}
      onClick={handleCardClick}
    >
      {!hideImage && (
        <div className={`overflow-hidden rounded-xl ${currentLayout.imageContainer} flex items-center justify-center`}>
          <img
            src={item.thumbnailUrl}
            alt={item.title}
            loading="lazy"
            decoding="async"
            sizes="(min-width: 1024px) 25vw, (min-width: 768px) 33vw, 100vw"
            className="max-w-full max-h-full object-contain"
            onError={() => setHideImage(true)}
          />
        </div>
      )}
      <div className={`flex flex-col justify-start flex-grow overflow-hidden ${currentLayout.contentContainer}`}>
        <div>
          <div className="flex items-center justify-between text-sm text-muted-foreground mb-2">
            <div className="flex items-center">
              {getIcon()}
              <span className="ml-2 capitalize">
                {item.type.replace("_", " ")}
              </span>
            </div>
            {item.metadata?.source_name === "Hugging Face Papers" && (
              <Badge
                variant="outline"
                className="text-xs px-2 py-0 h-5 flex items-center gap-1"
              >
                <TrendingUp className="h-3 w-3" />
                Trending
              </Badge>
            )}
          </div>

          <h3 className={`font-serif font-bold ${currentLayout.titleSize} mb-2 leading-tight group-hover:text-primary transition-colors ${titleClamp}`}>
            {item.title}
          </h3>

          {item.aiSummary && (
            <p className={`text-muted-foreground text-base ${summaryClamp} mb-3 leading-snug`}>
              {item.aiSummary}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between text-sm text-muted-foreground mt-2">
          <div className="font-medium truncate">
            {item.author || "Unknown"}
          </div>
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
