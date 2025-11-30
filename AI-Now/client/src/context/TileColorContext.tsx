import { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";

const API_BASE = import.meta.env.VITE_PYTHON_API_URL || "http://localhost:8000";

export type TileColorPalette =
  | "default"
  | "ocean"
  | "sunset"
  | "forest"
  | "monochrome"
  | "earth"
  | "colorblindSafe"
  | "highContrast";

interface TileColorContextType {
  palette: TileColorPalette;
  setPalette: (palette: TileColorPalette) => void;
  isLoading: boolean;
  isSaving: boolean;
  justSaved: boolean;
}

const TileColorContext = createContext<TileColorContextType | undefined>(undefined);

interface TileColorProviderProps {
  children: React.ReactNode;
}

// Color palette definitions - each palette defines colors for YouTube, Podcast, and Article tiles
// Format: { light: [bg, border, text], dark: [bg, border, text] }
export const PALETTE_DEFINITIONS: Record<
  TileColorPalette,
  {
    name: string;
    description: string;
    youtube: { light: string[]; dark: string[] };
    podcast: { light: string[]; dark: string[] };
    article: { light: string[]; dark: string[] };
  }
> = {
  default: {
    name: "Default",
    description: "Classic blue, green, and purple tones",
    youtube: {
      light: ["hsl(120, 40%, 92%)", "hsl(120, 40%, 85%)", "hsl(142, 70%, 20%)"],
      dark: ["hsl(175, 35%, 18%)", "hsl(175, 30%, 28%)", "hsl(150, 70%, 85%)"],
    },
    podcast: {
      light: ["hsl(270, 50%, 92%)", "hsl(270, 45%, 80%)", "hsl(275, 70%, 22%)"],
      dark: ["hsl(270, 40%, 20%)", "hsl(270, 35%, 30%)", "hsl(280, 65%, 90%)"],
    },
    article: {
      light: ["hsl(210, 65%, 93%)", "hsl(210, 55%, 78%)", "hsl(210, 70%, 20%)"],
      dark: ["hsl(220, 35%, 18%)", "hsl(220, 30%, 26%)", "hsl(210, 55%, 88%)"],
    },
  },
  ocean: {
    name: "Ocean",
    description: "Teal, cyan, and deep blue waves",
    youtube: {
      light: ["hsl(175, 50%, 90%)", "hsl(175, 45%, 80%)", "hsl(175, 70%, 20%)"],
      dark: ["hsl(175, 40%, 16%)", "hsl(175, 35%, 26%)", "hsl(175, 60%, 85%)"],
    },
    podcast: {
      light: ["hsl(240, 50%, 92%)", "hsl(240, 45%, 80%)", "hsl(240, 70%, 22%)"],
      dark: ["hsl(240, 40%, 18%)", "hsl(240, 35%, 28%)", "hsl(240, 55%, 88%)"],
    },
    article: {
      light: ["hsl(200, 60%, 92%)", "hsl(200, 50%, 80%)", "hsl(200, 70%, 20%)"],
      dark: ["hsl(200, 40%, 17%)", "hsl(200, 35%, 27%)", "hsl(200, 50%, 85%)"],
    },
  },
  sunset: {
    name: "Sunset",
    description: "Warm orange, coral, and magenta hues",
    youtube: {
      light: ["hsl(45, 80%, 92%)", "hsl(45, 70%, 80%)", "hsl(40, 70%, 22%)"],
      dark: ["hsl(40, 40%, 18%)", "hsl(40, 35%, 28%)", "hsl(45, 60%, 85%)"],
    },
    podcast: {
      light: ["hsl(280, 50%, 92%)", "hsl(280, 45%, 82%)", "hsl(280, 65%, 24%)"],
      dark: ["hsl(280, 35%, 18%)", "hsl(280, 30%, 28%)", "hsl(280, 55%, 88%)"],
    },
    article: {
      light: ["hsl(10, 70%, 93%)", "hsl(10, 60%, 80%)", "hsl(10, 65%, 22%)"],
      dark: ["hsl(10, 35%, 17%)", "hsl(10, 30%, 27%)", "hsl(10, 50%, 85%)"],
    },
  },
  forest: {
    name: "Forest",
    description: "Deep greens, moss, and olive tones",
    youtube: {
      light: ["hsl(100, 35%, 90%)", "hsl(100, 30%, 78%)", "hsl(100, 55%, 20%)"],
      dark: ["hsl(100, 30%, 16%)", "hsl(100, 25%, 26%)", "hsl(100, 40%, 80%)"],
    },
    podcast: {
      light: ["hsl(160, 40%, 90%)", "hsl(160, 30%, 78%)", "hsl(160, 50%, 22%)"],
      dark: ["hsl(160, 28%, 16%)", "hsl(160, 22%, 26%)", "hsl(160, 35%, 82%)"],
    },
    article: {
      light: ["hsl(35, 40%, 90%)", "hsl(35, 30%, 80%)", "hsl(35, 50%, 20%)"],
      dark: ["hsl(35, 25%, 16%)", "hsl(35, 20%, 26%)", "hsl(35, 35%, 82%)"],
    },
  },
  monochrome: {
    name: "Monochrome",
    description: "Clean grayscale and neutral tones",
    youtube: {
      light: ["hsl(0, 0%, 94%)", "hsl(0, 0%, 84%)", "hsl(0, 0%, 20%)"],
      dark: ["hsl(0, 0%, 18%)", "hsl(0, 0%, 28%)", "hsl(0, 0%, 88%)"],
    },
    podcast: {
      light: ["hsl(0, 0%, 91%)", "hsl(0, 0%, 80%)", "hsl(0, 0%, 22%)"],
      dark: ["hsl(0, 0%, 16%)", "hsl(0, 0%, 26%)", "hsl(0, 0%, 85%)"],
    },
    article: {
      light: ["hsl(220, 5%, 93%)", "hsl(220, 4%, 82%)", "hsl(220, 5%, 20%)"],
      dark: ["hsl(220, 5%, 17%)", "hsl(220, 4%, 27%)", "hsl(220, 5%, 87%)"],
    },
  },
  earth: {
    name: "Earth",
    description: "Brown, tan, and terracotta warmth",
    youtube: {
      light: ["hsl(20, 50%, 91%)", "hsl(20, 40%, 80%)", "hsl(20, 50%, 22%)"],
      dark: ["hsl(20, 25%, 17%)", "hsl(20, 20%, 27%)", "hsl(20, 40%, 82%)"],
    },
    podcast: {
      light: ["hsl(80, 30%, 90%)", "hsl(80, 25%, 80%)", "hsl(80, 55%, 24%)"],
      dark: ["hsl(80, 28%, 17%)", "hsl(80, 23%, 27%)", "hsl(80, 40%, 83%)"],
    },
    article: {
      light: ["hsl(40, 40%, 92%)", "hsl(40, 30%, 80%)", "hsl(40, 45%, 22%)"],
      dark: ["hsl(40, 22%, 17%)", "hsl(40, 17%, 27%)", "hsl(40, 32%, 82%)"],
    },
  },
  // Colorblind-safe: Uses blue/orange contrast (safe for deuteranopia/protanopia)
  // with distinct brightness levels for each content type
  colorblindSafe: {
    name: "Colorblind Safe",
    description: "Blue/orange palette optimized for color vision accessibility",
    youtube: {
      // Bright orange - easily distinguishable
      light: ["hsl(30, 85%, 92%)", "hsl(30, 80%, 78%)", "hsl(25, 90%, 25%)"],
      dark: ["hsl(25, 50%, 20%)", "hsl(25, 45%, 32%)", "hsl(30, 75%, 85%)"],
    },
    podcast: {
      // Deep blue - maximum contrast with orange
      light: ["hsl(215, 70%, 92%)", "hsl(215, 65%, 80%)", "hsl(220, 80%, 25%)"],
      dark: ["hsl(220, 45%, 18%)", "hsl(220, 40%, 28%)", "hsl(215, 60%, 88%)"],
    },
    article: {
      // Neutral gray with slight warmth - distinct brightness
      light: ["hsl(40, 15%, 95%)", "hsl(40, 12%, 85%)", "hsl(40, 20%, 22%)"],
      dark: ["hsl(40, 10%, 15%)", "hsl(40, 8%, 25%)", "hsl(40, 15%, 88%)"],
    },
  },
  // High contrast: Maximum luminance differences for visual impairments
  highContrast: {
    name: "High Contrast",
    description: "Maximum contrast for visual accessibility",
    youtube: {
      light: ["hsl(60, 100%, 88%)", "hsl(60, 100%, 40%)", "hsl(0, 0%, 0%)"],
      dark: ["hsl(60, 80%, 20%)", "hsl(60, 90%, 45%)", "hsl(60, 100%, 95%)"],
    },
    podcast: {
      light: ["hsl(200, 100%, 90%)", "hsl(200, 100%, 45%)", "hsl(0, 0%, 0%)"],
      dark: ["hsl(200, 70%, 18%)", "hsl(200, 90%, 50%)", "hsl(200, 100%, 95%)"],
    },
    article: {
      light: ["hsl(0, 0%, 96%)", "hsl(0, 0%, 50%)", "hsl(0, 0%, 0%)"],
      dark: ["hsl(0, 0%, 12%)", "hsl(0, 0%, 55%)", "hsl(0, 0%, 98%)"],
    },
  },
};

function applyPaletteToDocument(palette: TileColorPalette) {
  const root = document.documentElement;
  const colors = PALETTE_DEFINITIONS[palette];

  // Set CSS custom properties for each content type
  // YouTube
  root.style.setProperty("--tile-youtube-bg-light", colors.youtube.light[0]);
  root.style.setProperty("--tile-youtube-border-light", colors.youtube.light[1]);
  root.style.setProperty("--tile-youtube-text-light", colors.youtube.light[2]);
  root.style.setProperty("--tile-youtube-bg-dark", colors.youtube.dark[0]);
  root.style.setProperty("--tile-youtube-border-dark", colors.youtube.dark[1]);
  root.style.setProperty("--tile-youtube-text-dark", colors.youtube.dark[2]);

  // Podcast
  root.style.setProperty("--tile-podcast-bg-light", colors.podcast.light[0]);
  root.style.setProperty("--tile-podcast-border-light", colors.podcast.light[1]);
  root.style.setProperty("--tile-podcast-text-light", colors.podcast.light[2]);
  root.style.setProperty("--tile-podcast-bg-dark", colors.podcast.dark[0]);
  root.style.setProperty("--tile-podcast-border-dark", colors.podcast.dark[1]);
  root.style.setProperty("--tile-podcast-text-dark", colors.podcast.dark[2]);

  // Article
  root.style.setProperty("--tile-article-bg-light", colors.article.light[0]);
  root.style.setProperty("--tile-article-border-light", colors.article.light[1]);
  root.style.setProperty("--tile-article-text-light", colors.article.light[2]);
  root.style.setProperty("--tile-article-bg-dark", colors.article.dark[0]);
  root.style.setProperty("--tile-article-border-dark", colors.article.dark[1]);
  root.style.setProperty("--tile-article-text-dark", colors.article.dark[2]);
}

export function TileColorProvider({ children }: TileColorProviderProps) {
  const { user, fetchWithAuth, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();

  // Start with default, then load from localStorage/server as appropriate
  const [palette, setLocalPalette] = useState<TileColorPalette>("default");
  const [justSaved, setJustSaved] = useState(false);
  const hasInitialized = useRef(false);

  // Once auth resolves, decide what palette to use
  useEffect(() => {
    if (authLoading || hasInitialized.current) return;
    
    hasInitialized.current = true;
    
    if (user) {
      // User is logged in - use localStorage as temporary cache until server data loads
      const saved = localStorage.getItem("tileColorPalette") as TileColorPalette;
      if (saved && saved in PALETTE_DEFINITIONS) {
        setLocalPalette(saved);
        applyPaletteToDocument(saved);
      }
    } else {
      // Not logged in - always use default and clear any stale localStorage
      localStorage.removeItem("tileColorPalette");
      setLocalPalette("default");
      applyPaletteToDocument("default");
    }
  }, [authLoading, user]);

  // Fetch from server when logged in
  const { data: preferencesData, isLoading } = useQuery({
    queryKey: ["display-preferences"],
    queryFn: async () => {
      const response = await fetchWithAuth(`${API_BASE}/api/v1/users/me/preferences/display`, {
        method: "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json() as Promise<{ tileColorPalette: TileColorPalette }>;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });

  // Sync with server preferences when data loads
  useEffect(() => {
    if (preferencesData?.tileColorPalette) {
      const serverPalette = preferencesData.tileColorPalette as TileColorPalette;
      if (serverPalette && serverPalette in PALETTE_DEFINITIONS) {
        setLocalPalette(serverPalette);
        localStorage.setItem("tileColorPalette", serverPalette);
        applyPaletteToDocument(serverPalette);
      }
    }
  }, [preferencesData]);

  // Reset to default when user logs out (during same session)
  const prevUserRef = useRef(user);
  useEffect(() => {
    // User just logged out (was logged in, now not)
    if (prevUserRef.current && !user) {
      setLocalPalette("default");
      localStorage.removeItem("tileColorPalette");
      applyPaletteToDocument("default");
    }
    prevUserRef.current = user;
  }, [user]);

  // Save to server mutation
  const saveMutation = useMutation({
    mutationFn: async (newPalette: TileColorPalette) => {
      const response = await fetchWithAuth(`${API_BASE}/api/v1/users/me/preferences/display`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tileColorPalette: newPalette }),
      });
      if (!response.ok) {
        throw new Error(`${response.status}: ${response.statusText}`);
      }
      return response.json();
    },
    onSuccess: (_, newPalette) => {
      queryClient.setQueryData(["display-preferences"], { tileColorPalette: newPalette });
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    },
  });

  // Apply colors whenever palette changes
  useEffect(() => {
    applyPaletteToDocument(palette);
  }, [palette]);

  const setPalette = useCallback(
    (newPalette: TileColorPalette) => {
      setLocalPalette(newPalette);
      applyPaletteToDocument(newPalette);
      localStorage.setItem("tileColorPalette", newPalette);

      // Save to server if logged in
      if (user) {
        saveMutation.mutate(newPalette);
      }
    },
    [user, saveMutation]
  );

  const contextValue = useMemo(
    () => ({
      palette,
      setPalette,
      isLoading,
      isSaving: saveMutation.isPending,
      justSaved,
    }),
    [palette, setPalette, isLoading, saveMutation.isPending, justSaved]
  );

  return (
    <TileColorContext.Provider value={contextValue}>
      {children}
    </TileColorContext.Provider>
  );
}

export function useTileColor() {
  const context = useContext(TileColorContext);
  if (!context) {
    throw new Error("useTileColor must be used within a TileColorProvider");
  }
  return context;
}
