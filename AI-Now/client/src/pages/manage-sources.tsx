import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { ArrowLeft, Loader2, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { AppLogo } from "@/components/branding/AppLogo";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";

interface Source {
  key: string;
  name: string;
  channel: string;
  category: string;
  contentTypes: string[];
  defaultEnabled: boolean;
}

interface SourcePreference {
  sourceKey: string;
  enabled: boolean;
}

interface PreferencesResponse {
  preferences: SourcePreference[];
}

interface SourcesResponse {
  total: number;
  sources: Source[];
}

const CHANNEL_LABELS: Record<string, string> = {
  rss: "Article",
  youtube: "YT",
  scraper: "Article",
};

const CONTENT_TYPE_LABELS: Record<string, string> = {
  youtube_video: "YT",
  article: "Article",
  blog: "Article",
  news: "Article",
  research_lab: "Research",
  research_paper: "Research Papers",
};

const CATEGORY_LABELS: Record<string, string> = {
  venture: "Venture",
  frontier_model: "Frontier-Model Companies",
  learning: "Learning",
  applied_ai: "Applied AI",
  options: "Options",
};

const CATEGORY_ORDER = ["venture", "frontier_model", "learning", "applied_ai", "options"];

export default function ManageSources() {
  const [, navigate] = useLocation();
  const { user, isLoading: authLoading, fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  const [localPreferences, setLocalPreferences] = useState<Record<string, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const saveTimeoutRef = useRef<number | null>(null);
  const isInitialLoadRef = useRef<boolean>(true);
  const lastSavedPreferencesRef = useRef<Record<string, boolean>>({});

  const debugLog = useCallback(
    (...args: Parameters<typeof console.debug>) => {
      if (import.meta.env.DEV) {
        console.debug(...args);
      }
    },
    [],
  );

  // Fetch all available sources
  const { data: sourcesData, isLoading: sourcesLoading } = useQuery<SourcesResponse>({
    queryKey: ["sources"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/v1/sources`);
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
  });

  // Fetch user preferences
  const { data: preferencesData, isLoading: preferencesLoading } = useQuery<PreferencesResponse>({
    queryKey: ["user-preferences"],
    queryFn: async () => {
      const response = await fetchWithAuth(`${API_BASE}/api/v1/users/me/preferences/sources`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    enabled: !!user,
  });

  // Initialize local preferences when data loads (only on initial load)
  useEffect(() => {
    if (preferencesData?.preferences && isInitialLoadRef.current) {
      const prefs: Record<string, boolean> = {};
      preferencesData.preferences.forEach((pref) => {
        prefs[pref.sourceKey] = pref.enabled;
      });
      debugLog("Loaded user preferences", {
        totalSources: preferencesData.preferences.length,
        preferences: prefs,
      });
      setLocalPreferences(prefs);
      lastSavedPreferencesRef.current = prefs;
      isInitialLoadRef.current = false;
      debugLog("Initial load complete, auto-save now enabled");
    }
  }, [preferencesData, debugLog]);

  // Save preferences mutation
  const saveMutation = useMutation({
    mutationFn: async (preferences: Record<string, boolean>) => {
      debugLog("Saving preferences", preferences);
      debugLog("Enabled count", Object.values(preferences).filter(Boolean).length);

      const response = await fetchWithAuth(`${API_BASE}/api/v1/users/me/preferences/sources`, {
        method: "PUT",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ preferences }),
      });

      debugLog("Save response status", response.status);

      if (!response.ok) {
        const error = await response.text();
        console.error("Failed to save preferences:", error);
        throw new Error(`${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      debugLog("Preferences saved successfully", result);
      return result;
    },
    onSuccess: (data, variables) => {
      debugLog("Preferences mutation success", data);
      // Update the last saved state to prevent re-triggering save
      lastSavedPreferencesRef.current = variables;
      // Update cache optimistically instead of invalidating (prevents refetch)
      queryClient.setQueryData(["user-preferences"], (old: PreferencesResponse | undefined) => {
        if (!old) return old;
        return {
          ...old,
          preferences: Object.entries(variables).map(([sourceKey, enabled]) => ({
            sourceKey,
            enabled,
          })),
        };
      });
      setIsSaving(false);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    },
    onError: (error) => {
      console.error("Error saving preferences:", error);
      setIsSaving(false);
      alert(`Failed to save preferences: ${error instanceof Error ? error.message : 'Unknown error'}`);
    },
  });

  useEffect(() => {
    if (saveTimeoutRef.current !== null) {
      window.clearTimeout(saveTimeoutRef.current);
    }

    if (isInitialLoadRef.current) {
      debugLog("Skipping save: initial load");
      return;
    }

    if (Object.keys(localPreferences).length === 0) {
      debugLog("Skipping save: preferences not initialized");
      return;
    }

    if (preferencesLoading || isSaving || saveMutation.isPending) {
      debugLog("Skipping save: still loading or saving");
      return;
    }

    // Check if preferences actually changed from last saved state
    const hasChanges = Object.keys(localPreferences).some(
      (key) => localPreferences[key] !== lastSavedPreferencesRef.current[key]
    );

    if (!hasChanges) {
      debugLog("Skipping save: no changes from last saved state");
      return;
    }

    debugLog("Scheduling auto-save in 500ms");
    
    saveTimeoutRef.current = window.setTimeout(() => {
      debugLog("Auto-save triggered");
      setIsSaving(true);
      saveMutation.mutate(localPreferences);
    }, 500);

    return () => {
      if (saveTimeoutRef.current !== null) {
        window.clearTimeout(saveTimeoutRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localPreferences, preferencesLoading, isSaving]);

  const toggleSource = (sourceKey: string) => {
    setLocalPreferences((prev) => ({
      ...prev,
      [sourceKey]: !prev[sourceKey],
    }));
  };

  const toggleSourceGroup = (sourceKeys: string[]) => {
    setLocalPreferences((prev) => {
      // Determine if all sources in the group are currently enabled
      const allEnabled = sourceKeys.every(key => prev[key] ?? true);
      // Toggle all sources to the opposite state
      const updates: Record<string, boolean> = {};
      sourceKeys.forEach(key => {
        updates[key] = !allEnabled;
      });
      return { ...prev, ...updates };
    });
  };

  const handleSelectAll = () => {
    if (!sourcesData?.sources) return;
    const allEnabled: Record<string, boolean> = {};
    sourcesData.sources.forEach((source) => {
      allEnabled[source.key] = true;
    });
    setLocalPreferences(allEnabled);
  };

  const handleDeselectAll = () => {
    if (!sourcesData?.sources) return;
    const allDisabled: Record<string, boolean> = {};
    sourcesData.sources.forEach((source) => {
      allDisabled[source.key] = false;
    });
    setLocalPreferences(allDisabled);
  };

  // Group sources by category, then by name (combining same-name sources)
  const groupedSources = useMemo(() => {
    if (!sourcesData?.sources) return {};
    
    const categoryGroups: Record<string, Record<string, Source[]>> = {};
    
    // First group by category, then by name
    sourcesData.sources.forEach((source) => {
      const category = source.category || "other";
      if (!categoryGroups[category]) {
        categoryGroups[category] = {};
      }
      if (!categoryGroups[category][source.name]) {
        categoryGroups[category][source.name] = [];
      }
      categoryGroups[category][source.name].push(source);
    });
    
    return categoryGroups;
  }, [sourcesData]);

  const enabledCount = useMemo(() => {
    return Object.values(localPreferences).filter(Boolean).length;
  }, [localPreferences]);

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      navigate("/");
    }
  }, [user, authLoading, navigate]);

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isLoading = sourcesLoading || preferencesLoading;

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="px-6 py-3">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/")}
              className="justify-self-start"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Feed
            </Button>
            <AppLogo />
            <div className="justify-self-end">
              <ThemeToggle />
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="space-y-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold">Manage Content Sources</h1>
                {isSaving && (
                  <span className="text-sm text-muted-foreground inline-flex items-center gap-1.5">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Saving...
                  </span>
                )}
                {justSaved && (
                  <span className="text-sm text-green-500 inline-flex items-center gap-1.5">
                    <Check className="h-3 w-3" />
                    Saved
                  </span>
                )}
              </div>
              <p className="text-muted-foreground">
                Choose which sources you want to see in your feed. Changes are saved automatically.
              </p>
              {!isLoading && (
                <p className="text-sm text-muted-foreground">
                  {enabledCount} of {sourcesData?.total || 0} sources enabled
                </p>
              )}
            </div>
            {!isLoading && (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSelectAll}
                >
                  Select All
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDeselectAll}
                >
                  Deselect All
                </Button>
              </div>
            )}
          </div>

          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && (
            <div className="space-y-8">
              {Object.entries(groupedSources)
                .sort(([a], [b]) => {
                  const indexA = CATEGORY_ORDER.indexOf(a);
                  const indexB = CATEGORY_ORDER.indexOf(b);
                  if (indexA === -1 && indexB === -1) return a.localeCompare(b);
                  if (indexA === -1) return 1;
                  if (indexB === -1) return -1;
                  return indexA - indexB;
                })
                .map(([category, nameGroups]) => (
                  <div key={category} className="space-y-3">
                    <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
                      {CATEGORY_LABELS[category] || category}
                    </h2>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(nameGroups)
                        .sort(([nameA], [nameB]) => nameA.localeCompare(nameB))
                        .map(([name, sources]) => {
                          // Get all source keys for this name group
                          const sourceKeys = sources.map(s => s.key);
                          
                          // Check if all sources in this group are enabled
                          const allEnabled = sourceKeys.every(key => 
                            localPreferences[key] ?? sources.find(s => s.key === key)?.defaultEnabled ?? true
                          );
                          
                          // Build combined badge label
                          const badgeLabels = new Set<string>();
                          
                          sources.forEach((source) => {
                            if (source.name.toLowerCase().includes("trends") || source.name.toLowerCase().includes("trending")) {
                              badgeLabels.add("Trending");
                            } else if (source.contentTypes && source.contentTypes.length > 0) {
                              const primaryType = source.contentTypes[0];
                              const label = CONTENT_TYPE_LABELS[primaryType] || CHANNEL_LABELS[source.channel] || source.channel;
                              badgeLabels.add(label);
                            } else {
                              const label = CHANNEL_LABELS[source.channel] || source.channel;
                              badgeLabels.add(label);
                            }
                          });
                          
                          const badgeLabel = Array.from(badgeLabels).join("/");
                          
                          return (
                            <button
                              key={name}
                              onClick={() => toggleSourceGroup(sourceKeys)}
                              className={`px-3 py-1.5 rounded-full border text-sm transition-colors inline-flex items-center gap-1.5 ${
                                allEnabled
                                  ? "bg-primary text-primary-foreground border-primary shadow"
                                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                              }`}
                            >
                              <span>{name}</span>
                              <span className={`text-xs px-1.5 py-0.5 rounded ${
                                allEnabled
                                  ? "bg-primary-foreground/20"
                                  : "bg-muted"
                              }`}>
                                {badgeLabel}
                              </span>
                            </button>
                          );
                        })}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
