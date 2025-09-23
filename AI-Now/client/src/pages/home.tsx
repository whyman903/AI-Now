import { useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import MosaicFeed from "@/components/feed/MosaicFeed";
import { TabNavigation } from "@/components/navigation/TabNavigation";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { LabSidebar } from "@/components/layout/LabSidebar";
import { AppLogo } from "@/components/branding/AppLogo";
import { Plus } from "lucide-react";

interface LabFilter {
  id: string;
  label: string;
  category?: string | null;
  source_type?: string | null;
}

interface ContentTypeFilter {
  id: string;
  label: string;
  value: string;
}

const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";

export default function Home() {
  const [selectedLabs, setSelectedLabs] = useState<LabFilter[]>([]);
  const [selectedContentTypes, setSelectedContentTypes] = useState<ContentTypeFilter[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const labsQuery = useQuery({
    queryKey: ["lab_filters"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/v1/sources/filters/labs`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json() as Promise<{ labs: LabFilter[] }>;
    },
    staleTime: 5 * 60 * 1000,
  });

  const selectedAuthors = useMemo(
    () => selectedLabs.map((lab) => lab.label),
    [selectedLabs]
  );

  const contentTypes = useMemo<ContentTypeFilter[]>(
    () => [
      { id: "youtube_video", label: "Video", value: "youtube_video" },
      { id: "article", label: "Article", value: "article" },
    ],
    []
  );

  const selectedTypeValues = useMemo(
    () => selectedContentTypes.map((type) => type.value),
    [selectedContentTypes]
  );

  const hasActiveFilters = selectedLabs.length > 0 || selectedContentTypes.length > 0;

  const activeFilterSummary = useMemo(() => {
    const parts: string[] = [];
    if (selectedLabs.length) {
      parts.push(`labs: ${selectedLabs.map((lab) => lab.label).join(", ")}`);
    }
    if (selectedContentTypes.length) {
      parts.push(`types: ${selectedContentTypes.map((type) => type.label).join(", ")}`);
    }
    return parts.join(" • ");
  }, [selectedLabs, selectedContentTypes]);

  const clearAllFilters = () => {
    setSelectedLabs([]);
    setSelectedContentTypes([]);
  };

  const toggleLab = (lab: LabFilter) => {
    setSelectedLabs((prev) => {
      const exists = prev.some((item) => item.id === lab.id);
      if (exists) {
        return prev.filter((item) => item.id !== lab.id);
      }
      return [...prev, lab];
    });
  };

  const toggleContentType = (type: ContentTypeFilter) => {
    setSelectedContentTypes((prev) => {
      const exists = prev.some((item) => item.id === type.id);
      if (exists) {
        return prev.filter((item) => item.id !== type.id);
      }
      return [...prev, type];
    });
  };

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: [
      "content",
      selectedAuthors.length ? [...selectedAuthors].sort().join("|") : "",
      selectedTypeValues.length ? [...selectedTypeValues].sort().join("|") : "",
    ],
    queryFn: async ({ pageParam = 0 }) => {
      const LIMIT = 48;
      const params = new URLSearchParams({
        limit: LIMIT.toString(),
        offset: (pageParam * LIMIT).toString(),
      });
      selectedAuthors.forEach((author) => params.append("source", author));
      selectedTypeValues.forEach((type) => params.append("types", type));

      const response = await fetch(`${API_BASE}/api/v1/content?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage) return undefined;
      const total = Number((lastPage as any)?.total ?? 0);
      const limit = Number((lastPage as any)?.limit ?? 24);
      const nextIndex = allPages.length;
      const nextOffset = nextIndex * limit;
      return nextOffset < total ? nextIndex : undefined;
    },
    initialPageParam: 0,
    retry: false,
  });

  const { data: papersData } = useQuery({
    queryKey: ["research_papers"],
    queryFn: async () => {
      const params = new URLSearchParams({
        content_type: "research_paper",
        limit: "10",
        offset: "0",
      });
      const response = await fetch(`${API_BASE}/api/v1/content?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    retry: false,
  });

  const allContent = useMemo(() => {
    if (!data?.pages) return [];
    return data.pages.flatMap((page: any) => page?.items || []);
  }, [data]);

  const combined = useMemo(() => {
    const papers = ((papersData as any)?.items || []) as any[];
    const merged: any[] = [];
    const seen = new Set<string>();

    const pickKey = (item: any) =>
      item?.id || item?.metadata?.original_url || item?.url || null;

    for (const item of [...papers, ...allContent]) {
      if (!item) continue;
      const key = pickKey(item);
      if (key) {
        if (seen.has(key)) continue;
        seen.add(key);
      }
      merged.push(item);
    }

    return merged;
  }, [papersData, allContent]);

  const labs = labsQuery.data?.labs ?? [];

  return (
    <div className="min-h-screen bg-background flex">
      <div className="flex-1 flex flex-col">
        <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
          <div className="px-6 py-3">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
              <span className="block" aria-hidden="true" />
              <AppLogo />
              <div className="justify-self-end">
                <ThemeToggle />
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col">
          <TabNavigation>
            <div className="px-6 py-6 space-y-6">
              {hasActiveFilters && (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3 text-sm">
                  <span>
                    Filters applied{activeFilterSummary ? ` — ${activeFilterSummary}` : ""}.
                  </span>
                  <button
                    onClick={clearAllFilters}
                    className="text-primary hover:underline"
                  >
                    Clear filters
                  </button>
                </div>
              )}

              {isLoading && (
                <div className="mosaic-grid">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div
                      key={i}
                      className={`mosaic-item ${
                        i % 4 === 0 ? "size-large" : i % 3 === 0 ? "size-wide" : "size-medium"
                      } bg-muted animate-pulse`}
                    >
                      <div className="h-full w-full bg-gradient-to-br from-muted to-muted/60 rounded-lg" />
                    </div>
                  ))}
                </div>
              )}

              {!isLoading && combined.length === 0 && (
                <div className="text-center py-20">
                  <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                    <Plus className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-medium text-foreground mb-2">No content yet</h3>
                  <p className="text-muted-foreground mb-4">
                    Content is being aggregated. Check back in a few minutes.
                  </p>
                </div>
              )}

              {!isLoading && combined.length > 0 && <MosaicFeed items={combined} />}

              {!isLoading && allContent.length > 0 && (
                <div className="flex items-center justify-center pt-4">
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

      <LabSidebar
        labs={labs}
        isLoading={labsQuery.isLoading}
        selectedLabs={selectedLabs}
        onToggleLab={toggleLab}
        onClear={() => setSelectedLabs([])}
        contentTypes={contentTypes}
        selectedContentTypes={selectedContentTypes}
        onToggleContentType={toggleContentType}
        onClearContentTypes={() => setSelectedContentTypes([])}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
    </div>
  );
}
