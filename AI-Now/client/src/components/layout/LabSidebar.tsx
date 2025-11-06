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
            ? "flex items-center justify-between px-3 py-3"
            : "flex flex-col items-center gap-3 py-4"
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
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
          <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
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
                className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
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
                    className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
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
                  className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
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
                      className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
                        isActive
                          ? "bg-primary text-primary-foreground border-primary shadow"
                          : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                      }`}
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
