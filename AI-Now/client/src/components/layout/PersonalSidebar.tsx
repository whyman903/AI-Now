import { useState } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "@/hooks/useAuth";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import {
  Home,
  Bookmark,
  History,
  Folder,
  User,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Maximize2,
} from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import type { User as UserType, BookmarkFolder } from "@shared/schema";

interface PersonalSidebarProps {
  cardSize?: number;
  onCardSizeChange?: (size: number) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function PersonalSidebar({ 
  cardSize = 1, 
  onCardSizeChange, 
  collapsed = false, 
  onToggleCollapse 
}: PersonalSidebarProps) {
  const { user, isAuthenticated, logout } = useAuth();
  const [location] = useLocation();

  // Fetch user's bookmark folders
  const { data: folders = [] } = useQuery<BookmarkFolder[]>({
    queryKey: ["/api/bookmark-folders"],
    enabled: isAuthenticated,
  });

  // Fetch user stats
  const { data: bookmarks = [] } = useQuery({
    queryKey: ["/api/bookmarks"],
    enabled: isAuthenticated,
  });

  const { data: readingHistory = [] } = useQuery({
    queryKey: ["/api/reading-history"],
    enabled: isAuthenticated,
  });

  const userData = user as UserType;

  const navigationItems = [
    { path: "/", icon: Home, label: "Home", active: location === "/" },
    { path: "/bookmarks", icon: Bookmark, label: "Bookmarks", active: location === "/bookmarks" },
    { path: "/reading-history", icon: History, label: "Reading History", active: location === "/reading-history" },
  ];

  const renderAuthContent = () => {
    if (!isAuthenticated) {
      return (
        <div className="p-4">
          {!collapsed ? (
            <div className="text-center py-8">
              <User className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">Sign in to get started</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Access your personalized content
              </p>
              <Button onClick={() => window.location.href = "/login"} className="w-full">
                Sign In
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => window.location.href = "/login"}
                className="h-8 w-8 p-0"
              >
                <User className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      );
    }

    return (
      <>
        {!collapsed && (
          <>
            {/* User Profile Section */}
            <div className="p-4 border-b">
              <div className="flex items-center gap-3 mb-4">
                <Avatar className="h-10 w-10">
                  <AvatarImage src={userData?.profileImageUrl || undefined} />
                  <AvatarFallback>
                    {userData?.firstName?.[0] || userData?.email?.[0] || "U"}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium truncate">
                    {userData?.firstName} {userData?.lastName}
                  </h3>
                  <p className="text-sm text-muted-foreground truncate">
                    {userData?.email}
                  </p>
                </div>
              </div>

              {/* Quick Stats */}
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-center p-2 bg-muted/50 rounded">
                  <div className="font-medium">{bookmarks.length}</div>
                  <div className="text-muted-foreground">Bookmarks</div>
                </div>
                <div className="text-center p-2 bg-muted/50 rounded">
                  <div className="font-medium">{readingHistory.length}</div>
                  <div className="text-muted-foreground">Read</div>
                </div>
              </div>
            </div>
          </>
        )}
      </>
    );
  };

  return (
    <div className={`${collapsed ? 'w-16' : 'w-80'} border-l bg-background flex flex-col h-full transition-all duration-300`}>
      {/* Collapse Toggle */}
      <div className="p-4 border-b flex items-center justify-between">
        {!collapsed && <h3 className="font-medium">Navigation</h3>}
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleCollapse}
          className="h-8 w-8 p-0"
        >
          {collapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
      </div>

      {renderAuthContent()}

      {!collapsed && (
        <>
          {/* Card Size Control */}
          <div className="p-4 border-b">
            <div className="space-y-3">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Maximize2 className="h-4 w-4" />
                Card Size
              </Label>
              <Slider
                min={0.5}
                max={2.0}
                step={0.1}
                value={[cardSize]}
                onValueChange={(value) => onCardSizeChange?.(value[0])}
                className="w-full"
              />
              <div className="text-xs text-muted-foreground text-center">
                {Math.round(cardSize * 100)}%
              </div>
            </div>
          </div>
        </>
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Navigation */}
        <div className="p-4">
          {!collapsed && <h4 className="font-medium mb-3">Pages</h4>}
          <div className="space-y-1">
            {navigationItems.map((item) => (
              <Link key={item.path} href={item.path}>
                <Button
                  variant={item.active ? "secondary" : "ghost"}
                  className={`${collapsed ? 'w-8 h-8 p-0' : 'w-full justify-start'}`}
                  size="sm"
                  title={collapsed ? item.label : undefined}
                >
                  <item.icon className={`${collapsed ? '' : 'mr-2'} h-4 w-4`} />
                  {!collapsed && item.label}
                </Button>
              </Link>
            ))}
          </div>
        </div>

        {/* Bookmark Folders Quick Access */}
        {!collapsed && folders.length > 0 && (
          <div className="p-4 border-t">
            <h4 className="font-medium mb-3">Quick Access</h4>
            <div className="space-y-1">
              {folders.slice(0, 4).map((folder) => (
                <Link key={folder.id} href={`/bookmarks?folder=${folder.id}`}>
                  <Button variant="ghost" className="w-full justify-start" size="sm">
                    <Folder 
                      className="mr-2 h-4 w-4" 
                      style={{ color: folder.color }} 
                    />
                    <span className="truncate">{folder.name}</span>
                  </Button>
                </Link>
              ))}
              {folders.length > 4 && (
                <Link href="/bookmarks">
                  <Button variant="ghost" className="w-full justify-start text-xs" size="sm">
                    View all folders
                  </Button>
                </Link>
              )}
            </div>
          </div>
        )}

        {/* User Actions */}
        <div className="mt-auto p-4 border-t">
          <div className="space-y-1">
            {!collapsed ? (
              <>
                <Button variant="ghost" className="w-full justify-start" size="sm">
                  <Settings className="mr-2 h-4 w-4" />
                  Settings
                </Button>
                <Button 
                  variant="ghost" 
                  className="w-full justify-start" 
                  size="sm"
                  onClick={() => {
                    logout();
                    window.location.href = "/";
                  }}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign Out
                </Button>
              </>
            ) : (
              <div className="flex flex-col gap-1">
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title="Settings">
                  <Settings className="h-4 w-4" />
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm"
                  className="h-8 w-8 p-0"
                  title="Sign Out"
                  onClick={() => {
                    logout();
                    window.location.href = "/";
                  }}
                >
                  <LogOut className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}