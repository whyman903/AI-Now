import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { useAuth } from "@/hooks/useAuth";
import { PersonalSidebar } from "@/components/layout/PersonalSidebar";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import MosaicFeed from "@/components/feed/MosaicFeed";
import { Button } from "@/components/ui/button";
import { Clock, RefreshCw, Podcast, LogIn } from "lucide-react";

export default function ReadingHistory() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [, setLocation] = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setLocation("/login");
    }
  }, [isAuthenticated, authLoading, setLocation]);

  const { data: history, isLoading, refetch } = useQuery<any[]>({
    queryKey: ["/api/reading-history"],
    enabled: isAuthenticated,
    retry: false,
  });

  const handleRefresh = () => {
    refetch();
  };

  // Show loading state while checking authentication
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <LogIn className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-2">Login Required</h2>
          <p className="text-muted-foreground mb-4">You need to log in to access your reading history.</p>
          <Button onClick={() => setLocation("/login")}>
            <LogIn className="mr-2 h-4 w-4" />
            Log In
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex">
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Navigation */}
        <div className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
          <div className="px-6 py-3">
            <div className="flex items-center justify-between gap-4">
              {/* App Name */}
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                  <Podcast className="w-4 h-4 text-white" />
                </div>
                <h1 className="text-xl font-bold text-foreground">TrendCurate</h1>
              </div>

              <div className="flex items-center gap-2">
                <ThemeToggle />
              </div>
            </div>
          </div>
        </div>

        {/* Header */}
        <div className="border-b bg-background p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center">
                <Clock className="w-4 h-4 text-purple-600" />
              </div>
              <div>
                <h1 className="text-2xl font-bold">Reading History</h1>
                <p className="text-muted-foreground">
                  {history?.length || 0} {(history?.length || 0) === 1 ? 'item' : 'items'} read
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={handleRefresh}
              disabled={isLoading}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-6">
          {!isAuthenticated ? (
            <div className="text-center py-20">
              <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                <Clock className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium mb-2">Sign in to view reading history</h3>
              <p className="text-muted-foreground mb-4">
                Create an account to track your reading progress.
              </p>
              <Button onClick={() => window.location.href = "/login"}>
                Sign In
              </Button>
            </div>
          ) : isLoading ? (
            <div className="mosaic-grid">
              {[...Array(6)].map((_, i) => (
                <div key={i} className={`mosaic-item ${
                  i % 4 === 0 ? 'size-large' : i % 3 === 0 ? 'size-wide' : 'size-medium'
                } bg-muted animate-pulse`}>
                  <div className="h-full w-full bg-gradient-to-br from-muted to-muted/60 rounded-lg" />
                </div>
              ))}
            </div>
          ) : history && history.length > 0 ? (
            <MosaicFeed items={history} />
          ) : (
            <div className="text-center py-20">
              <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                <Clock className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium mb-2">No reading history yet</h3>
              <p className="text-muted-foreground mb-4">
                Start reading content to see your history here.
              </p>
              <Button onClick={() => window.location.href = "/"}>
                Explore Content
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Personal Sidebar - Right Side */}
      <PersonalSidebar 
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
    </div>
  );
}