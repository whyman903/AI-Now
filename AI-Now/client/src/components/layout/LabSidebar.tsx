import { useEffect, useMemo, useState, type FocusEvent, type FormEvent } from "react";
import { Loader2, Filter, ChevronLeft, ChevronRight, LogIn, LogOut, Settings } from "lucide-react";
import { Link } from "wouter";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

interface LabSidebarProps {
  labs: LabFilter[];
  isLoading?: boolean;
  selectedLabs: LabFilter[];
  onToggleLab: (lab: LabFilter) => void;
  onClear: () => void;
  contentTypes: ContentTypeFilter[];
  contentTypesLoading?: boolean;
  selectedContentTypes: ContentTypeFilter[];
  onToggleContentType: (type: ContentTypeFilter) => void;
  onClearContentTypes: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const CONTENT_TYPE_PILL_STYLES: Record<
  string,
  { base: string; active: string }
> = {
  // Match the mosaic tile palettes so the filter chips mirror card colors
  youtube_video: {
    base:
      "bg-[hsl(120,40%,92%)] border-[hsl(120,40%,85%)] text-[hsl(142,70%,20%)] hover:bg-[hsl(120,40%,90%)] hover:border-[hsl(120,40%,78%)] dark:bg-[hsl(175,35%,18%)] dark:border-[hsl(175,30%,28%)] dark:text-[hsl(150,70%,85%)] dark:hover:bg-[hsl(175,35%,22%)] dark:hover:border-[hsl(175,30%,34%)]",
    active:
      "bg-[hsl(120,40%,88%)] border-[hsl(120,40%,78%)] text-[hsl(142,70%,16%)] shadow-sm ring-2 ring-offset-2 ring-offset-background ring-[hsl(120,40%,62%)] dark:bg-[hsl(175,35%,24%)] dark:border-[hsl(175,30%,36%)] dark:text-[hsl(150,80%,90%)]",
  },
  article: {
    base:
      "bg-[hsl(210,65%,93%)] border-[hsl(210,55%,78%)] text-[hsl(210,70%,20%)] hover:bg-[hsl(210,65%,91%)] hover:border-[hsl(210,65%,70%)] dark:bg-[hsl(220,35%,18%)] dark:border-[hsl(220,30%,26%)] dark:text-[hsl(210,55%,88%)] dark:hover:bg-[hsl(220,35%,22%)] dark:hover:border-[hsl(220,30%,32%)]",
    active:
      "bg-[hsl(210,65%,88%)] border-[hsl(210,65%,70%)] text-[hsl(210,75%,16%)] shadow-sm ring-2 ring-offset-2 ring-offset-background ring-[hsl(210,65%,60%)] dark:bg-[hsl(220,35%,24%)] dark:border-[hsl(220,30%,34%)] dark:text-[hsl(210,65%,92%)]",
  },
  podcast: {
    base:
      "bg-[hsl(270,50%,92%)] border-[hsl(270,45%,80%)] text-[hsl(275,70%,22%)] hover:bg-[hsl(270,50%,90%)] hover:border-[hsl(270,50%,70%)] dark:bg-[hsl(270,40%,20%)] dark:border-[hsl(270,35%,30%)] dark:text-[hsl(280,65%,90%)] dark:hover:bg-[hsl(270,40%,24%)] dark:hover:border-[hsl(270,35%,36%)]",
    active:
      "bg-[hsl(270,50%,88%)] border-[hsl(270,50%,70%)] text-[hsl(275,80%,18%)] shadow-sm ring-2 ring-offset-2 ring-offset-background ring-[hsl(270,50%,64%)] dark:bg-[hsl(270,40%,26%)] dark:border-[hsl(270,35%,38%)] dark:text-[hsl(280,75%,92%)]",
  },
};

function getContentTypeButtonClasses(typeId: string, isActive: boolean) {
  const styles = CONTENT_TYPE_PILL_STYLES[typeId];
  if (styles) {
    return isActive ? styles.active : styles.base;
  }
  return isActive
    ? "bg-primary text-primary-foreground border-primary shadow ring-2 ring-primary/70 ring-offset-2 ring-offset-background"
    : "border-border text-muted-foreground hover:text-foreground hover:bg-muted";
}

export function LabSidebar({
  labs,
  isLoading = false,
  selectedLabs,
  onToggleLab,
  onClear,
  contentTypes,
  contentTypesLoading = false,
  selectedContentTypes,
  onToggleContentType,
  onClearContentTypes,
  collapsed,
  onToggleCollapse,
}: LabSidebarProps) {
  const auth = useAuth();
  const { clearError } = auth;
  const [isHovered, setIsHovered] = useState(false);
  const [showAuthForm, setShowAuthForm] = useState(false);
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const hasLabs = labs.length > 0;
  const showContentTypeSection = contentTypesLoading || contentTypes.length > 0;
  const selectionSummary = useMemo(() => {
    const sourcesPart = selectedLabs.length
      ? selectedLabs.map((lab) => lab.label).join(", ")
      : "All Orgs";
    const typesPart = selectedContentTypes.length
      ? selectedContentTypes.map((type) => type.label).join(", ")
      : "All content types";
    return `${sourcesPart} • ${typesPart}`;
  }, [selectedLabs, selectedContentTypes]);

  const isExpanded = !collapsed || isHovered;

  const handleMouseEnter = () => setIsHovered(true);
  const handleMouseLeave = () => setIsHovered(false);
  const handleFocus = () => setIsHovered(true);
  const handleBlur = (event: FocusEvent<HTMLElement>) => {
    const nextTarget = event.relatedTarget as Node | null;
    if (!nextTarget || !event.currentTarget.contains(nextTarget)) {
      setIsHovered(false);
    }
  };
  const handleToggleClick = () => {
    if (!collapsed) {
      setIsHovered(false);
    }
    onToggleCollapse();
  };

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    clearError();

    if (!email.trim() || !password.trim()) {
      setLocalError("Email and password are required.");
      return;
    }

    const success =
      authMode === "signin"
        ? await auth.login(email.trim(), password)
        : await auth.register(email.trim(), password, displayName.trim() || null);

    if (success) {
      setShowAuthForm(false);
      setEmail("");
      setPassword("");
      setDisplayName("");
    }
  };

  const handleLogout = async () => {
    await auth.logout();
    setShowAuthForm(false);
  };

  const authError = localError || auth.authError;
  const isAuthBusy = auth.isAuthenticating;
  const isGuest = !auth.user;

  useEffect(() => {
    if (!isGuest) {
      setShowAuthForm(false);
      setLocalError(null);
      clearError();
    }
  }, [isGuest, clearError]);

  return (
    <aside
      className={`hidden lg:flex flex-col border-l border-border transition-all duration-300 ease-in-out group flex-shrink-0 lg:sticky lg:top-0 lg:h-screen ${
        isExpanded
          ? "w-80 bg-background shadow-lg"
          : "w-16 bg-muted/70 hover:bg-muted/80"
      }`}
      role="complementary"
      aria-label="Labs sidebar"
      aria-expanded={isExpanded}
      tabIndex={0}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      <div
        className={`border-b border-border bg-background/90 backdrop-blur ${
          isExpanded
            ? "flex items-center justify-between px-2.5 py-2.5"
            : "flex flex-col items-center gap-2.5 py-3.5"
        }`}
      >
        <Button
          variant="ghost"
          size="icon"
          onClick={handleToggleClick}
          aria-label={collapsed ? "Expand filters" : "Collapse filters"}
          className={`h-8 w-8 transition-colors ${
            isExpanded
              ? "rounded-full text-muted-foreground hover:text-foreground"
              : "rounded-full border border-border bg-background text-foreground shadow-sm hover:bg-muted"
          }`}
        >
          {collapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
        {isExpanded ? (
          <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span>Filter</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span className="leading-none [writing-mode:vertical-rl] rotate-180">Filter</span>
          </div>
        )}
      </div>

      {isExpanded && (
        <div className="flex-1 overflow-y-auto px-3.5 py-5 space-y-5">
          <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-3.5">
            {auth.isLoading ? (
              <div className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Checking session…
              </div>
            ) : isGuest ? (
              <>
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Sign in to personalize
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Customize which sources you want to see in your feed!
                  </p>
                </div>

                {showAuthForm ? (
                  <form className="space-y-2" onSubmit={handleAuthSubmit}>
                    <Input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@example.com"
                      autoComplete="email"
                      required
                    />
                    <Input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Password"
                      autoComplete={authMode === "signin" ? "current-password" : "new-password"}
                      required
                    />
                    {authMode === "signup" && (
                      <Input
                        type="text"
                        value={displayName}
                        onChange={(event) => setDisplayName(event.target.value)}
                        placeholder="Display name (optional)"
                        autoComplete="name"
                      />
                    )}
                    {authError && (
                      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                        {authError}
                      </div>
                    )}
                    <Button type="submit" className="w-full" disabled={isAuthBusy}>
                      {isAuthBusy ? (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {authMode === "signin" ? "Signing in…" : "Creating account…"}
                        </span>
                      ) : authMode === "signin" ? (
                        "Sign in"
                      ) : (
                        "Create account"
                      )}
                    </Button>
                    <button
                      type="button"
                      className="w-full text-center text-xs text-muted-foreground underline-offset-4 transition hover:text-foreground hover:underline"
                      onClick={() => {
                        setAuthMode(authMode === "signin" ? "signup" : "signin");
                        setLocalError(null);
                        clearError();
                      }}
                      disabled={isAuthBusy}
                    >
                      {authMode === "signin"
                        ? "Need an account? Sign up"
                        : "Already registered? Sign in"}
                    </button>
                  </form>
                ) : (
                  <div className="space-y-3">
                    <Button
                      className="w-full"
                      onClick={() => {
                        setShowAuthForm(true);
                        setAuthMode("signin");
                        setLocalError(null);
                        clearError();
                      }}
                    >
                      <LogIn className="mr-2 h-4 w-4" />
                      Sign in
                    </Button>
                    <button
                      type="button"
                      className="w-full text-center text-xs text-muted-foreground underline-offset-4 transition hover:text-foreground hover:underline"
                      onClick={() => {
                        setShowAuthForm(true);
                        setAuthMode("signup");
                        setLocalError(null);
                        clearError();
                      }}
                    >
                      Create account instead
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Signed in</p>
                  <p className="text-sm font-semibold text-foreground">
                    {auth.user?.displayName || auth.user?.email}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Your source preferences are saved to your account.
                  </p>
                </div>
                <Link href="/manage-sources" className="block">
                  <Button variant="default" size="sm" className="w-full inline-flex items-center gap-2 justify-center">
                    <Settings className="h-4 w-4" />
                    Manage Sources
                  </Button>
                </Link>
                <Button variant="outline" size="sm" onClick={handleLogout} className="w-full inline-flex items-center gap-2 justify-center">
                  <LogOut className="h-4 w-4" />
                  Sign out
                </Button>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Selection</p>
            <p className="text-sm font-medium text-foreground">{selectionSummary}</p>
          </div>

          <div className="space-y-3">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Labs</p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={onClear}
                className={`px-2.5 py-1 rounded-full border text-sm transition-colors ${
                  selectedLabs.length
                    ? "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                    : "bg-primary text-primary-foreground border-primary shadow"
                }`}
              >
                All Orgs
              </button>
              {isLoading && (
                <span className="inline-flex items-center gap-2 text-xs text-muted-foreground px-2 py-1">
                  <Loader2 className="h-3 w-3 animate-spin" /> Loading…
                </span>
              )}
              {!isLoading && !hasLabs && (
                <span className="text-xs text-muted-foreground">No labs configured yet.</span>
              )}
              {labs.map((lab) => {
                const isActive = selectedLabs.some((selected) => selected.id === lab.id);
                return (
                  <button
                    key={lab.id}
                    onClick={() => onToggleLab(lab)}
                    className={`px-2.5 py-1 rounded-full border text-sm transition-colors ${
                      isActive
                        ? "bg-primary text-primary-foreground border-primary shadow"
                        : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    {lab.label}
                  </button>
                );
              })}
            </div>
          </div>

          {showContentTypeSection && (
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Content Types</p>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={onClearContentTypes}
                  className={`px-2.5 py-1 rounded-full border text-sm transition-colors ${
                    selectedContentTypes.length
                      ? "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                      : "bg-primary text-primary-foreground border-primary shadow"
                  }`}
                >
                  All types
                </button>
                {contentTypesLoading && (
                  <span className="inline-flex items-center gap-2 text-xs text-muted-foreground px-2 py-1">
                    <Loader2 className="h-3 w-3 animate-spin" /> Loading…
                  </span>
                )}
                {!contentTypesLoading && !contentTypes.length && (
                  <span className="text-xs text-muted-foreground">No content types available.</span>
                )}
                {contentTypes.map((type) => {
                  const isActive = selectedContentTypes.some(
                    (selected) => selected.id === type.id
                  );
                  return (
                    <button
                      key={type.id}
                      onClick={() => onToggleContentType(type)}
                      className={`px-2.5 py-1 rounded-full border text-sm font-medium transition-all ${getContentTypeButtonClasses(type.id, isActive)}`}
                    >
                      {type.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
