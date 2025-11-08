import { useMemo, useState, useEffect, useRef } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import MosaicFeed from "@/components/feed/MosaicFeed";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { LabSidebar } from "@/components/layout/LabSidebar";
import { AppLogo } from "@/components/branding/AppLogo";
import { Plus, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { trackSearch } from "@/lib/analytics";
import { ensureSessionRegistered } from "@/lib/session";
import { useAuth } from "@/hooks/useAuth";

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

interface SourcePreference {
  sourceKey: string;
  enabled: boolean;
}

interface PreferencesResponse {
  preferences: SourcePreference[];
}

export default function Home() {
  const { user, fetchWithAuth } = useAuth();
  const debugLog = (...args: Parameters<typeof console.debug>) => {
    if (import.meta.env.DEV) {
      console.debug(...args);
    }
  };
  const [selectedLabs, setSelectedLabs] = useState<LabFilter[]>([]);
  const [selectedContentTypes, setSelectedContentTypes] = useState<ContentTypeFilter[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [keywordFilter, setKeywordFilter] = useState("");
  const lastTrackedSearchKey = useRef<string | null>(null);
  const searchDebounceHandle = useRef<number | null>(null);
  const latestResultsCount = useRef<number>(0);

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

  const { data: preferencesData } = useQuery<PreferencesResponse>({
    queryKey: ["user-preferences"],
    queryFn: async () => {
      const response = await fetchWithAuth(`${API_BASE}/api/v1/users/me/preferences/sources`, {
        method: "GET",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    enabled: !!user,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });

  const enabledSourceKeys = useMemo(() => {
    if (!user) {
      debugLog("Anonymous user - no source filtering");
      return null;
    }
    
    if (!preferencesData?.preferences) {
      debugLog("Logged in but preferences not loaded yet");
      return null;
    }
    
    const enabled = preferencesData.preferences
      .filter((pref) => pref.enabled)
      .map((pref) => pref.sourceKey);
    
    debugLog("User preferences loaded", {
      totalSources: preferencesData.preferences.length,
      enabledCount: enabled.length,
      enabledSources: enabled,
    });
    
    return enabled;
  }, [user, preferencesData]);

  const selectedAuthors = useMemo(
    () => selectedLabs.map((lab) => lab.label),
    [selectedLabs]
  );

  const contentTypes = useMemo<ContentTypeFilter[]>(
    () => [
      { id: "youtube_video", label: "Video", value: "youtube_video" },
      { id: "article", label: "Article", value: "article" },
      { id: "podcast", label: "Podcast", value: "podcast" },
    ],
    []
  );

  const selectedTypeValues = useMemo(
    () => selectedContentTypes.map((type) => type.value),
    [selectedContentTypes]
  );

  useEffect(() => {
    ensureSessionRegistered({ force: true });
  }, []);

  const hasActiveFilters = selectedLabs.length > 0 || selectedContentTypes.length > 0 || keywordFilter.trim() !== "";

  const activeFilterSummary = useMemo(() => {
    const parts: string[] = [];
    if (selectedLabs.length) {
      parts.push(`labs: ${selectedLabs.map((lab) => lab.label).join(", ")}`);
    }
    if (selectedContentTypes.length) {
      parts.push(`types: ${selectedContentTypes.map((type) => type.label).join(", ")}`);
    }
    if (keywordFilter.trim()) {
      parts.push(`search: "${keywordFilter}"`);
    }
    return parts.join(" • ");
  }, [selectedLabs, selectedContentTypes, keywordFilter]);

  const clearAllFilters = () => {
    setSelectedLabs([]);
    setSelectedContentTypes([]);
    setKeywordFilter("");
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
    isFetching,
  } = useInfiniteQuery({
    queryKey: [
      "content",
      selectedAuthors.length ? [...selectedAuthors].sort().join("|") : "",
      selectedTypeValues.length ? [...selectedTypeValues].sort().join("|") : "",
      keywordFilter.trim(),
      user?.id || "anonymous",
      enabledSourceKeys === null ? "no-filter" : enabledSourceKeys.length ? [...enabledSourceKeys].sort().join("|") : "none",
    ],
    queryFn: async ({ pageParam = 0 }) => {
      const LIMIT = keywordFilter.trim() ? 100 : 48;
      const params = new URLSearchParams({
        limit: LIMIT.toString(),
        offset: (pageParam * LIMIT).toString(),
      });
      selectedAuthors.forEach((author) => params.append("source", author));
      selectedTypeValues.forEach((type) => params.append("types", type));
      
      if (user && enabledSourceKeys !== null) {
        if (enabledSourceKeys.length > 0) {
          enabledSourceKeys.forEach((sourceKey) => params.append("sources", sourceKey));
          debugLog("Applying source filter", enabledSourceKeys);
        } else {
          params.append("sources", "__none__");
          debugLog("User disabled all sources");
        }
      } else {
        debugLog("No source filtering (anonymous or loading)");
      }

      const url = `${API_BASE}/api/v1/content?${params.toString()}`;
      debugLog("Fetching content", url);

      const response = await fetch(url);
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
    queryKey: [
      "research_papers",
      user?.id || "anonymous",
      enabledSourceKeys === null ? "no-filter" : enabledSourceKeys.length ? [...enabledSourceKeys].sort().join("|") : "none",
    ],
    queryFn: async () => {
      const params = new URLSearchParams({
        content_type: "research_paper",
        limit: "10",
        offset: "0",
      });
      
      if (user && enabledSourceKeys !== null) {
        if (enabledSourceKeys.length > 0) {
          enabledSourceKeys.forEach((sourceKey) => params.append("sources", sourceKey));
          debugLog("Applying source filter to research papers", enabledSourceKeys);
        } else {
          params.append("sources", "__none__");
          debugLog("User disabled all sources for papers");
        }
      }
      
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

  const searchableContent = useMemo(
    () =>
      combined.map((item) => {
        const fields: string[] = [];
        if (typeof item?.title === "string") {
          fields.push(item.title.toLowerCase());
        }
        if (typeof item?.author === "string") {
          fields.push(item.author.toLowerCase());
        }
        if (typeof item?.metadata?.source_name === "string") {
          fields.push(item.metadata.source_name.toLowerCase());
        }

        return {
          item,
          haystack: fields.join(" "),
        };
      }),
    [combined]
  );

  const filteredContent = useMemo(() => {
    const trimmed = keywordFilter.trim();
    if (!trimmed) {
      return combined;
    }

    const keyword = trimmed.toLowerCase();
    return searchableContent
      .filter(({ haystack }) => haystack.includes(keyword))
      .map(({ item }) => item);
  }, [keywordFilter, searchableContent]);

  useEffect(() => {
    latestResultsCount.current = filteredContent.length;
  }, [filteredContent.length]);

  const isFiltering = isLoading || isFetching || isFetchingNextPage;

  useEffect(() => {
    if (keywordFilter.trim() && hasNextPage && !isFetchingNextPage && !isLoading) {
      if (filteredContent.length < 20) {
        fetchNextPage();
      }
    }
  }, [keywordFilter, filteredContent.length, hasNextPage, isFetchingNextPage, isLoading, fetchNextPage]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (searchDebounceHandle.current !== null) {
      window.clearTimeout(searchDebounceHandle.current);
    }

    const trimmedQuery = keywordFilter.trim();
    if (!trimmedQuery) {
      lastTrackedSearchKey.current = null;
      searchDebounceHandle.current = null;
      return;
    }

    const filtersPayload: Record<string, unknown> = {};
    if (selectedAuthors.length) {
      filtersPayload.labs = selectedAuthors;
    }
    if (selectedTypeValues.length) {
      filtersPayload.content_types = selectedTypeValues;
    }

    const trackingKey = JSON.stringify({
      query: trimmedQuery,
      labs: selectedAuthors,
      types: selectedTypeValues,
    });

    searchDebounceHandle.current = window.setTimeout(() => {
      if (lastTrackedSearchKey.current === trackingKey) {
        return;
      }

      trackSearch(trimmedQuery, {
        resultsCount: latestResultsCount.current,
        filters: Object.keys(filtersPayload).length ? filtersPayload : undefined,
      });

      lastTrackedSearchKey.current = trackingKey;
    }, 600);

    return () => {
      if (searchDebounceHandle.current !== null) {
        window.clearTimeout(searchDebounceHandle.current);
        searchDebounceHandle.current = null;
      }
    };
  }, [keywordFilter, selectedAuthors, selectedTypeValues]);

  const labs = labsQuery.data?.labs ?? [];

  return (
    <div className="min-h-screen bg-background flex">
      <div className="flex-1 flex flex-col">
        <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
          <div className="px-5 py-2.5">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
              <span className="block" aria-hidden="true" />
              <AppLogo />
              <div className="justify-self-end flex items-center gap-3">
                <div className="relative group">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-foreground pointer-events-none z-10" />
                  <Input
                    type="text"
                    placeholder="Search by title or org..."
                    value={keywordFilter}
                    onChange={(e) => setKeywordFilter(e.target.value)}
                    className="pl-8 pr-8 h-8 bg-transparent border-transparent group-hover:bg-background group-hover:border-border group-focus-within:bg-background group-focus-within:border-border transition-all duration-300 ease-in-out w-10 group-hover:w-56 group-focus-within:w-56"
                  />
                  {keywordFilter && (
                    <button
                      onClick={() => setKeywordFilter("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center transition-colors z-10"
                      aria-label="Clear search"
                    >
                      <X className="h-3 w-3 text-foreground" />
                    </button>
                  )}
                </div>
                <ThemeToggle />
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="px-5 py-5 space-y-6">
            {hasActiveFilters && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/10 px-3.5 py-2.5 text-sm">
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

            {!isLoading && filteredContent.length === 0 && combined.length === 0 && (
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

            {!isLoading && filteredContent.length === 0 && combined.length > 0 && (
              <div className="text-center py-20">
                <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                  <Plus className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">No results found</h3>
                <p className="text-muted-foreground mb-4">
                  No items match your search "{keywordFilter}".
                </p>
              </div>
            )}

            {!isLoading && filteredContent.length > 0 && (
              <MosaicFeed items={filteredContent} isFiltering={isFiltering} />
            )}

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
