import { useState } from "react";
import { cn } from "@/lib/utils";
import { MainChatInterface } from "@/components/chat/MainChatInterface";
import { Search, Home, MessageCircle } from "lucide-react";

interface Tab {
  id: string;
  label: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

interface TabNavigationProps {
  onContentFilter?: (content: any[]) => void;
  children: React.ReactNode; // This will be the main content (feed)
}

export function TabNavigation({ onContentFilter, children }: TabNavigationProps) {
  const [activeTab, setActiveTab] = useState("browse");

  const tabs: Tab[] = [
    {
      id: "browse",
      label: "Browse",
      icon: <Home className="h-4 w-4" />,
      content: children
    },
    {
      id: "search",
      label: "Search & Chat",
      icon: <MessageCircle className="h-4 w-4" />,
      content: (
        <div className="min-h-full flex flex-col">
          <MainChatInterface onContentFilter={onContentFilter} />
        </div>
      )
    }
  ];

  const activeTabData = tabs.find(tab => tab.id === activeTab);

  return (
    <div className="flex flex-col h-full">
      {/* Tab Bar */}
      <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="px-6">
          <div className="flex items-center gap-0 -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-all duration-200 relative group",
                  activeTab === tab.id
                    ? "border-primary text-primary bg-primary/5 shadow-sm"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/30 hover:border-border"
                )}
              >
                <span className={cn(
                  "transition-colors duration-200",
                  activeTab === tab.id ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                )}>
                  {tab.icon}
                </span>
                <span className="whitespace-nowrap">
                  {tab.label}
                </span>
                {activeTab === tab.id && (
                  <div className="absolute inset-x-0 bottom-0 h-0.5 bg-primary rounded-t-sm" />
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        <div className="h-full">
          {activeTabData?.content}
        </div>
      </div>
    </div>
  );
}