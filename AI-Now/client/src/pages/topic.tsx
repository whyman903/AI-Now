import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
// import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { isUnauthorizedError } from "@/lib/authUtils";
import MosaicFeed from "@/components/feed/MosaicFeed";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { TopicsBar } from "@/components/navigation/TopicsBar";
import { UserMenu } from "@/components/navigation/UserMenu";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Plus } from "lucide-react";
import type { User } from "@shared/schema";

interface TopicProps {
  params: { topic: string };
}

export default function Topic({ params }: TopicProps) {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const [cardSize, setCardSize] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["/api/content", params.topic],
    queryFn: async ({ pageParam = 0 }) => {
      const API_BASE = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';
      const LIMIT = 12;
      const response = await fetch(`${API_BASE}/api/v1/content?topic=${params.topic}&limit=${LIMIT}&offset=${pageParam * LIMIT}`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage) return undefined;
      const total = Number((lastPage as any)?.total ?? 0);
      const limit = Number((lastPage as any)?.limit ?? 12);
      const nextIndex = allPages.length; // 0-based pages
      const nextOffset = nextIndex * limit;
      return nextOffset < total ? nextIndex : undefined;
    },
    initialPageParam: 0,
    retry: false,
  });

  // Flatten all pages of content
  const content = useMemo(() => {
    return data?.pages?.flatMap(page => page?.items || []).map((item: any) => ({
      ...item,
      isBookmarked: false,
      userInteractions: []
    })) || [];
  }, [data]);

  // Infinite scroll disabled: use explicit Load More button for stability

  // Redirect to onboarding if user is authenticated but hasn't completed onboarding
  useEffect(() => {
    if (isAuthenticated && user && !(user as User).onboardingCompleted) {
      window.location.href = "/onboarding";
    }
  }, [isAuthenticated, user]);

  const handleRefresh = () => {
    refetch();
  };

  // Update CSS custom properties for card sizing and text scaling
  useEffect(() => {
    const root = document.documentElement;
    const baseSize = 280;
    const baseHeight = 180;
    const newSize = Math.round(baseSize * cardSize);
    const newHeight = Math.round(baseHeight * cardSize);
    
    root.style.setProperty('--mosaic-card-size', `${newSize}px`);
    root.style.setProperty('--mosaic-card-height', `${newHeight}px`);
    root.style.setProperty('--mosaic-text-scale', cardSize.toString());
  }, [cardSize]);

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navigation */}
      <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container mx-auto px-3 py-2">
          <div className="flex items-center justify-between gap-4">
            {/* Size Control */}
            <div className="flex items-center gap-3">
              <Label htmlFor="size-slider" className="text-sm font-medium whitespace-nowrap">
                Size:
              </Label>
              <Slider
                id="size-slider"
                min={0.5}
                max={2.0}
                step={0.1}
                value={[cardSize]}
                onValueChange={(value) => setCardSize(value[0])}
                className="w-24"
              />
            </div>

            <div className="flex items-center gap-2">
              <ThemeToggle />
              <UserMenu />
            </div>
          </div>
        </div>
      </div>

      {/* Topics Bar */}
      <TopicsBar onSearch={setSearchQuery} />

      {/* Main Content */}
      <div className="container mx-auto px-3 py-6">
        {/* Loading State */}
        {isLoading && (
          <div className="mosaic-grid">
            {[...Array(12)].map((_, i) => (
              <div key={i} className={`mosaic-item ${
                i % 4 === 0 ? 'size-large' : i % 3 === 0 ? 'size-wide' : 'size-medium'
              } bg-muted animate-pulse`}>
                <div className="h-full w-full bg-gradient-to-br from-muted to-muted/60 rounded-lg" />
              </div>
            ))}
          </div>
        )}

        {/* Feed Items */}
        {!isLoading && content && (
          <>
            {content.length === 0 ? (
              <div className="text-center py-20">
                <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                  <Plus className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">
                  No content available for {params.topic.replace('-', ' ')}
                </h3>
                <p className="text-muted-foreground mb-4">
                  Content is being aggregated. Please check back in a few minutes.
                </p>
              </div>
            ) : (
              <MosaicFeed items={content} />
            )}
          </>
        )}

        {/* Manual Load More to avoid eager auto-loading */}
        {!isLoading && content && content.length > 0 && (
          <div className="flex items-center justify-center mt-8">
            {hasNextPage ? (
              <button
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="px-4 py-2 text-sm rounded-md border hover:bg-muted disabled:opacity-60"
              >
                {isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            ) : (
              <div className="text-xs text-muted-foreground">No more results</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
