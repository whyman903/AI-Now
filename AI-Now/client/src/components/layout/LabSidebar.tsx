import { useMemo } from "react";
import { Loader2, Filter, ChevronLeft, ChevronRight } from "lucide-react";

import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";

interface LabFilter {
  id: string;
  label: string;
  category?: string | null;
  source_type?: string | null;
}

interface LabSidebarProps {
  labs: LabFilter[];
  isLoading?: boolean;
  selectedLabs: LabFilter[];
  onToggleLab: (lab: LabFilter) => void;
  onClear: () => void;
  cardSize: number;
  onCardSizeChange: (size: number) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function LabSidebar({
  labs,
  isLoading = false,
  selectedLabs,
  onToggleLab,
  onClear,
  cardSize,
  onCardSizeChange,
  collapsed,
  onToggleCollapse,
}: LabSidebarProps) {
  const hasLabs = labs.length > 0;
  const selectionSummary = useMemo(() => {
    if (!selectedLabs.length) {
      return "All sources";
    }
    return selectedLabs.map((lab) => lab.label).join(", ");
  }, [selectedLabs]);

  return (
    <aside
      className={`hidden lg:flex flex-col border-l border-border bg-background transition-all duration-300 ease-in-out ${
        collapsed ? "w-14" : "w-80"
      }`}
    >
      <div className="flex items-center justify-between px-2 py-3 border-b border-border">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="h-7 w-7"
        >
          {collapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
        {!collapsed && (
          <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span>Labs</span>
          </div>
        )}
      </div>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Selection</p>
            <p className="text-sm font-medium text-foreground">{selectionSummary}</p>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">Card size</span>
              <span className="text-xs text-muted-foreground">{cardSize.toFixed(1)}x</span>
            </div>
            <Slider
              className="w-full"
              min={0.8}
              max={1.4}
              step={0.1}
              value={[cardSize]}
              onValueChange={(value) => onCardSizeChange(value[0] ?? cardSize)}
            />
          </div>

          <div className="space-y-3">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Sources</p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={onClear}
                className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${
                  selectedLabs.length
                    ? "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                    : "bg-primary text-primary-foreground border-primary shadow"
                }`}
              >
                All sources
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
        </div>
      )}
    </aside>
  );
}
