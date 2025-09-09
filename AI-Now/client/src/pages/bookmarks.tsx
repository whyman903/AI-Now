import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Folder, FolderOpen, Edit2, Trash2, MoreVertical, BookmarkX, Podcast, LogIn } from "lucide-react";
import { useLocation } from "wouter";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/hooks/useAuth";
import { PersonalSidebar } from "@/components/layout/PersonalSidebar";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ContentItem, BookmarkFolder } from "@shared/schema";

interface BookmarkWithFolder extends ContentItem {
  bookmarkId: string;
  notes?: string;
  folderId?: string;
  isBookmarked: boolean;
  userInteractions: any[];
}

export default function Bookmarks() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [, setLocation] = useLocation();
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [editingFolder, setEditingFolder] = useState<BookmarkFolder | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderColor, setNewFolderColor] = useState("#3b82f6");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setLocation("/login");
    }
  }, [isAuthenticated, authLoading, setLocation]);

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
          <p className="text-muted-foreground mb-4">You need to log in to access your bookmarks.</p>
          <Button onClick={() => setLocation("/login")}>
            <LogIn className="mr-2 h-4 w-4" />
            Log In
          </Button>
        </div>
      </div>
    );
  }

  // Fetch folders
  const { data: folders = [] } = useQuery<BookmarkFolder[]>({
    queryKey: ["/api/bookmark-folders"],
    enabled: isAuthenticated,
  });

  // Fetch bookmarks
  const { data: bookmarks = [], isLoading } = useQuery<BookmarkWithFolder[]>({
    queryKey: ["/api/bookmarks", selectedFolderId],
    enabled: isAuthenticated,
    queryFn: async () => {
      const url = selectedFolderId 
        ? `/api/bookmarks?folderId=${selectedFolderId}`
        : "/api/bookmarks";
      return apiRequest("GET", url);
    },
  });

  // Create folder mutation
  const createFolderMutation = useMutation({
    mutationFn: async (data: { name: string; color: string; description?: string }) => {
      return apiRequest("POST", "/api/bookmark-folders", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bookmark-folders"] });
      setShowCreateFolder(false);
      setNewFolderName("");
      setNewFolderColor("#3b82f6");
      toast({
        title: "Folder created",
        description: "Your bookmark folder has been created.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to create folder.",
        variant: "destructive",
      });
    },
  });

  // Update folder mutation
  const updateFolderMutation = useMutation({
    mutationFn: async ({ id, ...data }: { id: string; name: string; color: string }) => {
      return apiRequest("PATCH", `/api/bookmark-folders/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bookmark-folders"] });
      setEditingFolder(null);
      toast({
        title: "Folder updated",
        description: "Your bookmark folder has been updated.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to update folder.",
        variant: "destructive",
      });
    },
  });

  // Delete folder mutation
  const deleteFolderMutation = useMutation({
    mutationFn: async (folderId: string) => {
      return apiRequest("DELETE", `/api/bookmark-folders/${folderId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bookmark-folders"] });
      queryClient.invalidateQueries({ queryKey: ["/api/bookmarks"] });
      if (selectedFolderId === editingFolder?.id) {
        setSelectedFolderId(null);
      }
      toast({
        title: "Folder deleted",
        description: "Your bookmark folder has been deleted.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to delete folder.",
        variant: "destructive",
      });
    },
  });

  // Remove bookmark mutation
  const removeBookmarkMutation = useMutation({
    mutationFn: async (contentItemId: string) => {
      return apiRequest("DELETE", `/api/bookmarks/${contentItemId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bookmarks"] });
      toast({
        title: "Bookmark removed",
        description: "The bookmark has been removed.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to remove bookmark.",
        variant: "destructive",
      });
    },
  });

  // Move bookmark mutation
  const moveBookmarkMutation = useMutation({
    mutationFn: async ({ bookmarkId, folderId }: { bookmarkId: string; folderId?: string }) => {
      return apiRequest("PATCH", `/api/bookmarks/${bookmarkId}/move`, { folderId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bookmarks"] });
      toast({
        title: "Bookmark moved",
        description: "The bookmark has been moved to the folder.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to move bookmark.",
        variant: "destructive",
      });
    },
  });

  const handleCreateFolder = () => {
    if (newFolderName.trim()) {
      createFolderMutation.mutate({
        name: newFolderName.trim(),
        color: newFolderColor,
      });
    }
  };

  const handleUpdateFolder = () => {
    if (editingFolder && newFolderName.trim()) {
      updateFolderMutation.mutate({
        id: editingFolder.id,
        name: newFolderName.trim(),
        color: newFolderColor,
      });
    }
  };

  const handleDeleteFolder = (folder: BookmarkFolder) => {
    if (confirm(`Are you sure you want to delete "${folder.name}"? Bookmarks will be moved to "All Bookmarks".`)) {
      deleteFolderMutation.mutate(folder.id);
    }
  };

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
            <div>
              <h1 className="text-2xl font-bold">
                {selectedFolderId
                  ? folders.find(f => f.id === selectedFolderId)?.name || "Bookmarks"
                  : "All Bookmarks"}
              </h1>
              <p className="text-muted-foreground">
                {bookmarks.length} {bookmarks.length === 1 ? 'item' : 'items'}
              </p>
            </div>
            <Button
              onClick={() => setShowCreateFolder(true)}
              className="ml-4"
            >
              <Plus className="mr-2 h-4 w-4" />
              New Folder
            </Button>
          </div>
        </div>

        {/* Folder Tabs */}
        <div className="border-b bg-background px-6">
          <div className="flex items-center gap-1 -mb-px">
            <button
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                selectedFolderId === null 
                  ? 'border-primary text-primary' 
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setSelectedFolderId(null)}
            >
              All Bookmarks
            </button>
            {folders.map((folder) => (
              <button
                key={folder.id}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                  selectedFolderId === folder.id 
                    ? 'border-primary text-primary' 
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
                onClick={() => setSelectedFolderId(folder.id)}
              >
                <Folder className="h-4 w-4" style={{ color: folder.color }} />
                {folder.name}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-2 h-5 w-5 p-0 opacity-0 group-hover:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onClick={() => {
                        setEditingFolder(folder);
                        setNewFolderName(folder.name);
                        setNewFolderColor(folder.color || "#3b82f6");
                      }}
                    >
                      <Edit2 className="mr-2 h-4 w-4" />
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => handleDeleteFolder(folder)}
                      className="text-destructive"
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-muted-foreground">Loading bookmarks...</div>
            </div>
          ) : bookmarks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <BookmarkX className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No bookmarks in this folder</p>
              <p className="text-sm text-muted-foreground mt-2">
                Save content to see it here
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {bookmarks.map((bookmark) => (
                <div
                  key={bookmark.id}
                  className="border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => window.open(bookmark.sourceUrl, '_blank')}
                >
                  <div className="flex justify-between items-start mb-2">
                    <Badge variant="secondary" className="text-xs">
                      {bookmark.type.replace('_', ' ')}
                    </Badge>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {folders.length > 0 && (
                          <>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                moveBookmarkMutation.mutate({
                                  bookmarkId: bookmark.bookmarkId,
                                  folderId: undefined,
                                });
                              }}
                            >
                              Move to All Bookmarks
                            </DropdownMenuItem>
                            {folders.map((folder) => (
                              <DropdownMenuItem
                                key={folder.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  moveBookmarkMutation.mutate({
                                    bookmarkId: bookmark.bookmarkId,
                                    folderId: folder.id,
                                  });
                                }}
                              >
                                Move to {folder.name}
                              </DropdownMenuItem>
                            ))}
                          </>
                        )}
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation();
                            removeBookmarkMutation.mutate(bookmark.id);
                          }}
                          className="text-destructive"
                        >
                          <BookmarkX className="mr-2 h-4 w-4" />
                          Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <h3 className="font-semibold mb-2 line-clamp-2">{bookmark.title}</h3>
                  {bookmark.aiSummary && (
                    <p className="text-sm text-muted-foreground line-clamp-3 mb-2">
                      {bookmark.aiSummary}
                    </p>
                  )}
                  {bookmark.notes && (
                    <p className="text-sm italic text-muted-foreground">
                      Note: {bookmark.notes}
                    </p>
                  )}
                  <div className="flex justify-between items-center mt-4 text-xs text-muted-foreground">
                    <span>{bookmark.author || 'Unknown'}</span>
                    {bookmark.publishedAt && (
                      <span>{new Date(bookmark.publishedAt).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create/Edit Folder Dialog */}
        <Dialog open={showCreateFolder || !!editingFolder} onOpenChange={(open) => {
          if (!open) {
            setShowCreateFolder(false);
            setEditingFolder(null);
            setNewFolderName("");
            setNewFolderColor("#3b82f6");
          }
        }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingFolder ? 'Edit Folder' : 'Create New Folder'}</DialogTitle>
              <DialogDescription>
                {editingFolder ? 'Update your bookmark folder details.' : 'Create a new folder to organize your bookmarks.'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">Folder Name</label>
                <Input
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  placeholder="Enter folder name"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Color</label>
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="color"
                    value={newFolderColor}
                    onChange={(e) => setNewFolderColor(e.target.value)}
                    className="h-10 w-20"
                  />
                  <span className="text-sm text-muted-foreground">{newFolderColor}</span>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setShowCreateFolder(false);
                  setEditingFolder(null);
                  setNewFolderName("");
                  setNewFolderColor("#3b82f6");
                }}
              >
                Cancel
              </Button>
              <Button onClick={editingFolder ? handleUpdateFolder : handleCreateFolder}>
                {editingFolder ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Personal Sidebar - Right Side */}
      <PersonalSidebar 
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
    </div>
  );
}