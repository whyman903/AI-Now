import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/hooks/useAuth";
import { chatService } from "@/services/chatService";
import type { ChatMessage, ContentResult } from "@/types/chat";
import {
  Send,
  MessageCircle,
  Search,
  Sparkles,
  BookOpen,
  TrendingUp,
  Calendar,
  Bookmark,
  History,
  ExternalLink,
  Clock,
} from "lucide-react";

interface MainChatInterfaceProps {
  onContentFilter?: (content: any[]) => void;
}

export function MainChatInterface({ onContentFilter }: MainChatInterfaceProps) {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const { toast } = useToast();
  const { user } = useAuth();

  // Clean, focused suggested queries
  const suggestedQueries = [
    "Find articles about machine learning",
    "Show my bookmarked startup content", 
    "What did I read this week?",
    "Summarize AI trends from my reading",
    "What topics am I most interested in?",
    "Find content similar to blockchain"
  ];

  // Chat mutation using the new service layer
  const chatMutation = useMutation({
    mutationFn: async (userMessage: string) => {
      if (!user?.id) throw new Error('User not authenticated');
      
      return chatService.chat({
        message: userMessage,
        userId: user.id,
        context: {
          includeBookmarks: true,
          includeReadingHistory: true,
          timeRange: 'all',
        },
      });
    },
    onSuccess: (data, userMessage) => {
      const assistantMessage: ChatMessage = {
        id: Date.now().toString(),
        type: 'assistant',
        message: data.response,
        timestamp: new Date(),
        results: data.results,
        sources: data.sources,
      };
      setChatHistory(prev => [...prev, assistantMessage]);
      
      // Filter content based on results if provided
      if (data.results && data.results.length > 0 && onContentFilter) {
        onContentFilter(data.results);
      }
    },
    onError: (error: any) => {
      console.error('Chat error:', error);
      toast({
        title: "Error",
        description: error.message || "Failed to process your request",
        variant: "destructive",
      });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || chatMutation.isPending) return;

    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      message: message.trim(),
      timestamp: new Date(),
    };
    setChatHistory(prev => [...prev, userMessage]);
    
    // Send to API
    chatMutation.mutate(message.trim());
    setMessage("");
  };

  const handleSuggestedQuery = (query: string) => {
    setMessage(query);
  };

  return (
    <div className="flex flex-col h-full">
      {chatHistory.length === 0 ? (
        // Initial state - centered, clean search
        <div className="flex-1 flex flex-col items-center justify-center max-w-2xl mx-auto px-6">
          <div className="w-full space-y-6">
            {/* Main Search Input */}
            <form onSubmit={handleSubmit} className="relative">
              <Input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ask about your content..."
                className="w-full h-14 pl-12 pr-16 text-base border-2 rounded-xl shadow-sm focus:shadow-md transition-all"
                disabled={chatMutation.isPending}
              />
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Button 
                type="submit" 
                disabled={!message.trim() || chatMutation.isPending}
                size="sm"
                className="absolute right-2 top-1/2 transform -translate-y-1/2 h-10 w-10 p-0 rounded-lg"
              >
                {chatMutation.isPending ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </form>

            {/* Suggested Queries */}
            <div className="space-y-3">
              <p className="text-sm font-medium text-muted-foreground text-center">Try asking:</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {suggestedQueries.map((query, index) => (
                  <button
                    key={index}
                    onClick={() => handleSuggestedQuery(query)}
                    className="px-4 py-2 text-sm bg-muted hover:bg-muted/80 rounded-full transition-colors border border-border/50 hover:border-border"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        // Conversation state
        <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
          {/* Compact search input */}
          <div className="p-6 border-b">
            <form onSubmit={handleSubmit} className="relative">
              <Input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Follow up question..."
                className="w-full h-12 pl-12 pr-16 rounded-xl"
                disabled={chatMutation.isPending}
              />
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Button 
                type="submit" 
                disabled={!message.trim() || chatMutation.isPending}
                size="sm"
                className="absolute right-2 top-1/2 transform -translate-y-1/2 h-8 w-8 p-0 rounded-lg"
              >
                {chatMutation.isPending ? (
                  <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white" />
                ) : (
                  <Send className="h-3 w-3" />
                )}
              </Button>
            </form>
          </div>

          {/* Chat History */}
          <ScrollArea className="flex-1 p-6">
            <div className="space-y-8">
              {chatHistory.map((msg) => (
                <div key={msg.id} className="space-y-4">
                  {msg.type === 'user' ? (
                    <div className="flex justify-end">
                      <div className="bg-primary text-primary-foreground px-4 py-3 rounded-2xl rounded-br-md max-w-[80%]">
                        <div className="text-sm">{msg.message}</div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="bg-muted/50 px-4 py-3 rounded-2xl rounded-bl-md">
                        <div className="text-sm leading-relaxed whitespace-pre-wrap">{msg.message}</div>
                      </div>
                      
                      {/* Content Results */}
                      {msg.results && msg.results.length > 0 && (
                        <div className="space-y-3">
                          <div className="text-sm font-medium text-muted-foreground">
                            Found {msg.results.length} relevant items
                          </div>
                          <div className="grid gap-3">
                            {msg.results.slice(0, 3).map((result) => (
                              <div 
                                key={result.id} 
                                className="border rounded-xl p-4 hover:bg-muted/30 transition-colors cursor-pointer"
                                onClick={() => window.open(result.sourceUrl, '_blank')}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="flex-1 space-y-2">
                                    <div className="font-medium text-sm leading-tight">{result.title}</div>
                                    {result.author && (
                                      <div className="text-xs text-muted-foreground">by {result.author}</div>
                                    )}
                                    {result.aiSummary && (
                                      <div className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                                        {result.aiSummary}
                                      </div>
                                    )}
                                    <div className="flex items-center gap-2">
                                      <Badge variant="outline" className="text-xs">
                                        {result.type.replace('_', ' ')}
                                      </Badge>
                                      {result.relevanceScore && (
                                        <div className="text-xs text-muted-foreground">
                                          {Math.round(result.relevanceScore * 100)}% match
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                  <ExternalLink className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                </div>
                              </div>
                            ))}
                          </div>
                          {msg.results.length > 3 && (
                            <div className="text-xs text-muted-foreground">
                              And {msg.results.length - 3} more results...
                            </div>
                          )}
                        </div>
                      )}
                      
                      {/* Sources */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {msg.sources.map((source, idx) => (
                            <Badge key={idx} variant="secondary" className="text-xs">
                              {source}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}