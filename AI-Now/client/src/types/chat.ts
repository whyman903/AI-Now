// API contract for Python FastAPI backend

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  message: string;
  timestamp: Date;
  results?: ContentResult[];
  sources?: string[];
}

export interface ContentResult {
  id: string;
  title: string;
  type: string;
  author?: string;
  aiSummary?: string;
  sourceUrl: string;
  publishedAt?: string;
  thumbnailUrl?: string;
  relevanceScore?: number;
}

export interface ChatRequest {
  message: string;
  userId: string;
  context?: {
    includeBookmarks?: boolean;
    includeReadingHistory?: boolean;
    timeRange?: 'day' | 'week' | 'month' | 'all';
    contentTypes?: string[];
  };
}

export interface ChatResponse {
  response: string;
  results: ContentResult[];
  sources: string[];
  queryType: 'search' | 'summary' | 'recommendation' | 'analysis';
  metadata?: {
    totalResults: number;
    searchTime: number;
    confidence: number;
  };
}

export interface UserAnalysis {
  topTopics: string[];
  readingStats: {
    totalItems: number;
    bookmarks: number;
    readingHistory: number;
    thisWeek: number;
    thisMonth: number;
  };
  contentTypes: Record<string, number>;
  readingPatterns: {
    avgReadingTime: number;
    preferredContentLength: 'short' | 'medium' | 'long';
    peakReadingHours: number[];
  };
  interests: {
    topic: string;
    confidence: number;
    trendDirection: 'increasing' | 'stable' | 'decreasing';
  }[];
}

// API endpoints that will be implemented in Python/FastAPI
export interface ChatAPI {
  // Main chat endpoint
  chat(request: ChatRequest): Promise<ChatResponse>;
  
  // User analysis
  getUserAnalysis(userId: string): Promise<UserAnalysis>;
  
  // Content search
  searchContent(userId: string, query: string, filters?: {
    contentTypes?: string[];
    timeRange?: string;
    limit?: number;
  }): Promise<ContentResult[]>;
  
  // Content recommendations
  getRecommendations(userId: string, limit?: number): Promise<ContentResult[]>;
  
  // Similar content
  findSimilarContent(userId: string, contentId: string, limit?: number): Promise<ContentResult[]>;
}