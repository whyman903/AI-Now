import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings, Plus, Check, Home, Bookmark, History, User as UserIcon } from "lucide-react";
import { Link, useLocation } from "wouter";
import { useAuth } from "@/hooks/useAuth";
import type { User } from "@shared/schema";

interface SidebarProps {
  user?: User;
}

export default function Sidebar({ user }: SidebarProps) {
  const [location] = useLocation();
  const { isAuthenticated } = useAuth();
  const interests = user?.interests || [];

  const navigationItems = [
    { path: "/", icon: Home, label: "Home", public: true },
    { path: "/bookmarks", icon: Bookmark, label: "Bookmarks", public: false },
    { path: "/reading-history", icon: History, label: "Reading History", public: false },
  ];

  return (
    <div className="space-y-4">
      {/* Navigation */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Navigation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {navigationItems.map((item) => {
            const isActive = location === item.path;
            const canAccess = item.public || isAuthenticated;
            
            if (!canAccess) return null;
            
            return (
              <Link key={item.path} href={item.path}>
                <Button 
                  variant={isActive ? "default" : "ghost"} 
                  className="w-full justify-start"
                  size="sm"
                >
                  <item.icon className="h-4 w-4 mr-2" />
                  {item.label}
                </Button>
              </Link>
            );
          })}
          
          {!isAuthenticated && (
            <div className="pt-2 border-t border-gray-200">
              <Button 
                onClick={() => window.location.href = '/login'}
                variant="outline" 
                size="sm" 
                className="w-full"
              >
                <UserIcon className="h-4 w-4 mr-2" />
                Sign In
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Interests (for authenticated users) */}
      {isAuthenticated && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Your Interests</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {interests.length === 0 ? (
                <p className="text-sm text-gray-500">
                  No interests selected. Add some to get personalized content!
                </p>
              ) : (
                interests.map((interest) => (
                  <div
                    key={interest}
                    className="flex items-center justify-between p-2 bg-blue-50 rounded-lg border border-blue-200"
                  >
                    <span className="text-sm font-medium text-blue-900">{interest}</span>
                    <Check className="h-3 w-3 text-blue-600" />
                  </div>
                ))
              )}
            </div>
            
            <Button variant="outline" size="sm" className="w-full">
              <Settings className="h-4 w-4 mr-2" />
              Manage Interests
            </Button>

            <div className="pt-4 border-t border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Quick Stats</h3>
              <div className="space-y-2 text-sm text-gray-600">
                <div className="flex justify-between">
                  <span>Items read today</span>
                  <span className="font-medium">0</span>
                </div>
                <div className="flex justify-between">
                  <span>Bookmarks</span>
                  <span className="font-medium">0</span>
                </div>
                <div className="flex justify-between">
                  <span>Feed updated</span>
                  <span className="font-medium text-green-600">Just now</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
