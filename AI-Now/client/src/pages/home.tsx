import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
// import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { isUnauthorizedError } from "@/lib/authUtils";
import MosaicFeed from "@/components/feed/MosaicFeed";
import { PersonalSidebar } from "@/components/layout/PersonalSidebar";
import { TabNavigation } from "@/components/navigation/TabNavigation";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Plus, Podcast } from "lucide-react";
import type { User } from "@shared/schema";

export default function Home() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const [cardSize, setCardSize] = useState(1);
  const [filteredContent, setFilteredContent] = useState<any[] | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["/api/content"],
    queryFn: async ({ pageParam = 0 }) => {
      const API_BASE = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';
      const LIMIT = 24;
      const response = await fetch(`${API_BASE}/api/v1/content?limit=${LIMIT}&offset=${pageParam * LIMIT}&exclude_type=research_paper`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    getNextPageParam: (lastPage, allPages) => {
      const MAX_PAGES = 10; // hard cap to avoid runaway loading
      if (!lastPage) return undefined;
      if (allPages.length >= MAX_PAGES) return undefined;
      const total = Number((lastPage as any)?.total ?? 0);
      const limit = Number((lastPage as any)?.limit ?? 24);
      const nextIndex = allPages.length; // 0-based pages
      const nextOffset = nextIndex * limit;
      return nextOffset < total ? nextIndex : undefined;
    },
    initialPageParam: 0,
    retry: false,
  });

  // Fetch papers separately so the main feed can exclude them
  const { data: papersData } = useQuery({
    queryKey: ["research_papers"],
    queryFn: async () => {
      const API_BASE = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE}/api/v1/content?content_type=research_paper&limit=10&offset=0`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    retry: false,
  });

  // Flatten all pages of content
  const allContent = useMemo(() => {
    if (!data?.pages) return [];
    return data.pages.flatMap(page => page?.items || []);
  }, [data]);

  // Use filtered content if available, otherwise show all content
  const content = filteredContent || allContent;
  const combined = useMemo(() => {
    const papers = (papersData as any)?.items || [];
    return [...papers, ...content];
  }, [papersData, content]);

  // Infinite scroll disabled: use explicit Load More button for stability

  // No mount-time prefetch; rely on scroll sentinel to load more.

  // Onboarding redirect disabled - skip onboarding for now
  // useEffect(() => {
  //   if (isAuthenticated && user && !(user as User).onboardingCompleted) {
  //     // Redirect to onboarding
  //     window.location.href = "/onboarding";
  //   }
  // }, [isAuthenticated, user]);

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
    <div className="min-h-screen bg-background flex">
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Navigation */}
        <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
          <div className="px-6 py-3">
            <div className="flex items-center justify-between gap-4">
              {/* App Name */}
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                  <Podcast className="w-4 h-4 text-white" />
                </div>
                <h1 className="text-xl font-bold text-foreground">TrendCurate</h1>
              </div>

              <div className="flex items-center gap-2">
                <ThemeToggle />
              </div>
            </div>
          </div>
        </div>

        {/* Tab Navigation with Content */}
        <div className="flex-1 flex flex-col">
          <TabNavigation>
            <div className="px-6 py-6">
              {/* Content Filter Status */}
              {filteredContent && (
                <div className="mb-4 p-3 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Plus className="h-4 w-4 text-primary" />
                    <span className="text-sm font-medium">
                      Showing {filteredContent.length} filtered results
                    </span>
                  </div>
                  <button
                    onClick={() => setFilteredContent(null)}
                    className="text-sm text-primary hover:underline"
                  >
                    Show all content
                  </button>
                </div>
              )}

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
              {!isLoading && combined && (
                <>
                  {combined.length === 0 ? (
                    <div className="text-center py-20">
                      <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                        <Plus className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <h3 className="text-lg font-medium text-foreground mb-2">No content available</h3>
                      <p className="text-muted-foreground mb-4">
                        Content is being aggregated. Please check back in a few minutes.
                      </p>
                    </div>
                  ) : (
                    <MosaicFeed items={combined} />
                  )}
                </>
              )}

              {/* Manual Load More to avoid eager auto-loading */}
              {!isLoading && !filteredContent && allContent && allContent.length > 0 && (
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
          </TabNavigation>
        </div>
      </div>

      {/* Personal Sidebar - Right Side */}
      <PersonalSidebar 
        cardSize={cardSize}
        onCardSizeChange={setCardSize}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
    </div>
  );
}
