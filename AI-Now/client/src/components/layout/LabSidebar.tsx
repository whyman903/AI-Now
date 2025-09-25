import { useMemo, useState, type FocusEvent } from "react";
import { Loader2, Filter, ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

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
  const [isHovered, setIsHovered] = useState(false);
  const hasLabs = labs.length > 0;
  const showContentTypeSection = contentTypesLoading || contentTypes.length > 0;
  const selectionSummary = useMemo(() => {
    const sourcesPart = selectedLabs.length
      ? selectedLabs.map((lab) => lab.label).join(", ")
      : "All labs";
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
            <span>Labs</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span className="leading-none [writing-mode:vertical-rl] rotate-180">Labs</span>
          </div>
        )}
      </div>

      {isExpanded && (
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
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
                All labs
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
