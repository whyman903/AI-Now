import { useState } from "react";
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


  // Define a new layout structure for items
  type LayoutItem = {
    item: ContentItemWithInteractions;
    gridClass: string;
    cardLayout: 'hero' | 'regular' | 'wide';
  };

  const createStructuredLayout = (items: ContentItemWithInteractions[]): LayoutItem[] => {
    const layoutItems: LayoutItem[] = [];
    const youtubeVideos = items.filter(item => item.type === 'youtube_video');
    const otherContent = items.filter(item => item.type !== 'youtube_video');

    let otherIndex = 0;
    // For each YouTube video, try to pair it with two articles
    for (const video of youtubeVideos) {
      // Add the YouTube video, spanning 2x2
      layoutItems.push({
        item: video,
        gridClass: 'md:col-span-2 lg:col-span-2 lg:row-span-2',
        cardLayout: 'hero'
      });

      // Add up to two articles to sit alongside the video
      for (let i = 0; i < 2; i++) {
        if (otherIndex < otherContent.length) {
          layoutItems.push({
            item: otherContent[otherIndex],
            gridClass: 'lg:col-span-1 lg:row-span-1',
            cardLayout: 'regular'
          });
          otherIndex++;
        }
      }
    }

    // Add any remaining articles at the end, filling the grid
    while (otherIndex < otherContent.length) {
      layoutItems.push({
        item: otherContent[otherIndex],
        gridClass: 'lg:col-span-1 lg:row-span-1',
        cardLayout: 'regular'
      });
      otherIndex++;
    }

    return layoutItems;
  };

  const structuredLayout = createStructuredLayout(regularContent);

  return (
    <div className="p-2 sm:p-3 lg:p-4">
      <div className="grid gap-2 grid-cols-1 md:grid-cols-2 lg:grid-cols-4 items-start grid-flow-row-dense">
        
        {/* Papers sidebar */}
        {papers.length > 0 && (
          <div className="relative z-10 pb-2 lg:col-start-4 lg:col-span-1">
            <div className="pb-2 mb-3">
              <h2 className="text-lg font-bold">Research Papers</h2>
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
          </div>
        )}

        {/* Content cards */}
        {structuredLayout.map(({ item, gridClass, cardLayout }) => (
          <div key={item.id} className={gridClass}>
            <ArticleCard 
              item={item} 
              layout={cardLayout} 
            />
          </div>
        ))}
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

  const layoutConfig = {
    hero: {
      flexDirection: "flex-col",
      imageContainer: "w-full",
      contentContainer: hasThumbnail ? "pt-4" : "",
      titleSize: "text-3xl",
      summaryClamp: "line-clamp-3",
      minHeight: "min-h-[220px]",
    },
    wide: {
      flexDirection: "flex-col",
      imageContainer: "w-full",
      contentContainer: hasThumbnail ? "pt-4" : "",
      titleSize: "text-xl",
      summaryClamp: "line-clamp-2",
      minHeight: "min-h-[180px]",
    },
    regular: {
      flexDirection: "flex-col",
      imageContainer: "w-full",
      contentContainer: hasThumbnail ? "pt-4" : "",
      titleSize: "text-lg",
      summaryClamp: "line-clamp-2",
      minHeight: "min-h-[150px]",
    },
  };

  const currentLayout = layoutConfig[layout];

  return (
    <div
      className={`group cursor-pointer flex ${currentLayout.flexDirection} border p-4 rounded-2xl shadow-none hover:shadow-md transition-shadow duration-300 w-full h-full ${currentLayout.minHeight} ${getCardStyleClasses()}`}
      onClick={handleCardClick}
    >
      {hasThumbnail && (
        <div
          className={`overflow-hidden rounded-xl ${currentLayout.imageContainer}`}
          style={{ aspectRatio: '16 / 9' }}
        >
          <img
            src={item.thumbnailUrl}
            alt={item.title}
            loading="lazy"
            decoding="async"
            sizes="(min-width: 1024px) 50vw, (min-width: 768px) 66vw, 100vw"
            className="w-full h-auto max-h-72 object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              e.currentTarget.style.display = "none";
              e.currentTarget.parentElement?.style && 
                (e.currentTarget.parentElement.style.display = "none");
            }}
          />
        </div>
      )}
      <div className={`flex flex-col justify-start flex-grow ${currentLayout.contentContainer}`}>
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

          <h3 className={`font-serif font-bold ${currentLayout.titleSize} mb-2 leading-tight group-hover:text-primary transition-colors`}>
            {item.title}
          </h3>

          {item.aiSummary && (
            <p className={`text-muted-foreground text-base ${currentLayout.summaryClamp} mb-3 leading-snug`}>
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
