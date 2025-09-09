import { useState } from "react";
import { Link, useLocation } from "wouter";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

const topics = [
  { id: "all", label: "All", path: "/" },
  { id: "personal-finance", label: "Personal Finance", path: "/topic/personal-finance" },
  { id: "health", label: "Health", path: "/topic/health" },
  { id: "style", label: "Style", path: "/topic/style" },
  { id: "sports", label: "Sports", path: "/topic/sports" },
  { id: "tech", label: "Tech", path: "/topic/tech" },
  { id: "science", label: "Science", path: "/topic/science" }
];

interface TopicsBarProps {
  onSearch?: (query: string) => void;
}

export function TopicsBar({ onSearch }: TopicsBarProps) {
  const [location] = useLocation();
  const [searchQuery, setSearchQuery] = useState("");

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);
    onSearch?.(query);
  };

  return (
    <div className="bg-background border-b border-border">
      <div className="container mx-auto px-3 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Topics */}
          <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
            {topics.map((topic) => (
              <Link key={topic.id} href={topic.path}>
                <button
                  className={cn(
                    "px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors",
                    location === topic.path
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  )}
                >
                  {topic.label}
                </button>
              </Link>
            ))}
          </div>

          {/* Search */}
          <div className="relative min-w-[250px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search content..."
              value={searchQuery}
              onChange={handleSearchChange}
              className="pl-10 bg-background"
            />
          </div>
        </div>
      </div>
    </div>
  );
}