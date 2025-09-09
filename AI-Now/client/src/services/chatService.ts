import type { ChatAPI, ChatRequest, ChatResponse, UserAnalysis, ContentResult } from '@/types/chat';

// Configuration for different environments
const API_CONFIG = {
  // Will point to your Python FastAPI backend
  PYTHON_BACKEND_URL: import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000',
  USE_MOCK: import.meta.env.VITE_USE_MOCK_API === 'true' || !import.meta.env.VITE_PYTHON_API_URL,
};

// Mock implementation for development
class MockChatService implements ChatAPI {
  private delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async chat(request: ChatRequest): Promise<ChatResponse> {
    await this.delay(800); // Simulate API delay
    
    const query = request.message.toLowerCase();
    
    // Mock different types of responses based on query content
    if (query.includes('interest') || query.includes('topic')) {
      return this.mockInterestResponse(request);
    } else if (query.includes('summary') || query.includes('summarize')) {
      return this.mockSummaryResponse(request);
    } else if (query.includes('recommend') || query.includes('similar')) {
      return this.mockRecommendationResponse(request);
    } else if (query.includes('bookmark') || query.includes('saved')) {
      return this.mockBookmarkResponse(request);
    } else {
      return this.mockSearchResponse(request);
    }
  }

  private mockSearchResponse(request: ChatRequest): ChatResponse {
    const mockResults: ContentResult[] = [
      {
        id: '1',
        title: 'Machine Learning Fundamentals for Beginners',
        type: 'article',
        author: 'Dr. Sarah Chen',
        aiSummary: 'Comprehensive guide covering basic ML concepts, algorithms, and practical applications.',
        sourceUrl: 'https://example.com/ml-fundamentals',
        publishedAt: '2024-01-15T10:00:00Z',
        relevanceScore: 0.95,
      },
      {
        id: '2',
        title: 'The Future of AI in Healthcare',
        type: 'research_paper',
        author: 'Medical AI Research Team',
        aiSummary: 'Analysis of AI applications in medical diagnosis, treatment planning, and patient care.',
        sourceUrl: 'https://example.com/ai-healthcare',
        publishedAt: '2024-01-10T14:30:00Z',
        relevanceScore: 0.87,
      },
    ];

    return {
      response: `I found ${mockResults.length} items related to "${request.message}". Here are the most relevant results:

**Machine Learning Fundamentals for Beginners** by Dr. Sarah Chen
This comprehensive guide covers basic ML concepts, algorithms, and practical applications. Perfect for getting started with machine learning.

**The Future of AI in Healthcare** by Medical AI Research Team  
Analysis of AI applications in medical diagnosis, treatment planning, and patient care. Shows promising trends in medical AI.

Would you like me to find more specific content or analyze these results further?`,
      results: mockResults,
      sources: ['Your reading history', 'Bookmarked articles'],
      queryType: 'search',
      metadata: {
        totalResults: mockResults.length,
        searchTime: 0.45,
        confidence: 0.91,
      },
    };
  }

  private mockInterestResponse(request: ChatRequest): ChatResponse {
    return {
      response: `Based on your reading history and bookmarks, here are your main interests:

**Top Topics:**
1. Artificial Intelligence & Machine Learning
2. Software Development & Programming  
3. Startup Ecosystem & Business Strategy
4. Cybersecurity & Privacy
5. Web Development & Frontend Technologies

**Reading Patterns:**
• You've engaged with 47 pieces of content this month
• 62% of your bookmarks are about AI/ML topics
• You prefer medium-length articles (5-10 min reads)
• Most active reading time: 9-11 AM and 7-9 PM

**Content Preferences:**
• Research papers: 35%
• Technical articles: 40% 
• Podcast episodes: 15%
• Video content: 10%

Your interests show a strong focus on emerging technologies with practical applications. You seem to enjoy both theoretical foundations and real-world implementations.`,
      results: [],
      sources: ['Reading patterns analysis', 'Bookmark categorization'],
      queryType: 'analysis',
      metadata: {
        totalResults: 0,
        searchTime: 0.32,
        confidence: 0.94,
      },
    };
  }

  private mockSummaryResponse(request: ChatRequest): ChatResponse {
    const mockResults: ContentResult[] = [
      {
        id: '3',
        title: 'GPT-4 Architecture Deep Dive',
        type: 'article',
        author: 'AI Research Weekly',
        aiSummary: 'Technical analysis of GPT-4\'s transformer architecture and training methodology.',
        sourceUrl: 'https://example.com/gpt4-architecture',
        publishedAt: '2024-01-20T16:00:00Z',
      },
      {
        id: '4',
        title: 'Scaling Kubernetes in Production',
        type: 'youtube_video',
        author: 'DevOps Masterclass',
        aiSummary: 'Best practices for scaling Kubernetes clusters and managing microservices at scale.',
        sourceUrl: 'https://youtube.com/watch?v=example',
        publishedAt: '2024-01-18T11:00:00Z',
      },
    ];

    return {
      response: `Here's a summary of your recent reading activity:

**This Week's Highlights:**
You've been diving deep into AI architecture and infrastructure scaling. Your reading shows a pattern of exploring both cutting-edge AI research and practical implementation challenges.

**Key Content:**
• **GPT-4 Architecture Deep Dive** - Technical analysis of transformer architecture
• **Scaling Kubernetes in Production** - DevOps best practices for microservices

**Emerging Themes:**
• Large language model architectures
• Production infrastructure scaling  
• AI safety and alignment
• Microservices deployment strategies

**Insight:** Your content mix suggests you're working on or planning AI projects that need robust production infrastructure. You might be interested in content about MLOps and AI deployment patterns.`,
      results: mockResults,
      sources: ['Last 7 days reading history', 'Recent bookmarks'],
      queryType: 'summary',
      metadata: {
        totalResults: mockResults.length,
        searchTime: 0.28,
        confidence: 0.88,
      },
    };
  }

  private mockRecommendationResponse(request: ChatRequest): ChatResponse {
    const mockResults: ContentResult[] = [
      {
        id: '5',
        title: 'Vector Databases for AI Applications',
        type: 'article',
        author: 'Database Weekly',
        aiSummary: 'Comprehensive guide to vector databases and their role in AI/ML applications.',
        sourceUrl: 'https://example.com/vector-databases',
        publishedAt: '2024-01-22T09:00:00Z',
        relevanceScore: 0.92,
      },
    ];

    return {
      response: `Based on your interests in **AI, machine learning, and infrastructure**, here are some recommendations:

**Trending in Your Interest Areas:**
• **Vector Databases for AI Applications** - Given your focus on AI architecture, this covers the data storage layer that's becoming critical for RAG and embedding-based systems.

**Why This Matches Your Profile:**
• You've shown interest in both AI research and practical implementation
• Your recent reading about GPT-4 architecture suggests interest in the full AI stack
• Vector databases are the missing piece between AI models and production systems

**Suggested Next Steps:**
• Explore content about RAG (Retrieval-Augmented Generation) systems
• Look into embedding models and similarity search
• Consider reading about AI product development lifecycle

Would you like me to find more content about any specific aspect of AI infrastructure?`,
      results: mockResults,
      sources: ['Interest analysis', 'Trending content'],
      queryType: 'recommendation',
      metadata: {
        totalResults: mockResults.length,
        searchTime: 0.52,
        confidence: 0.89,
      },
    };
  }

  private mockBookmarkResponse(request: ChatRequest): ChatResponse {
    const mockResults: ContentResult[] = [
      {
        id: '6',
        title: 'Building RAG Systems with LangChain',
        type: 'article',
        author: 'LangChain Team',
        aiSummary: 'Step-by-step guide to building retrieval-augmented generation systems.',
        sourceUrl: 'https://example.com/rag-langchain',
        publishedAt: '2024-01-25T12:00:00Z',
      },
    ];

    return {
      response: `Here are your recent bookmarks related to "${request.message}":

**Your Bookmarked Content:**
• **Building RAG Systems with LangChain** - Saved 3 days ago
  Step-by-step guide to building retrieval-augmented generation systems. This seems very relevant to your current interests!

**Bookmark Insights:**
• You have 23 total bookmarks
• 65% are about AI/ML topics
• Most recently bookmarked: RAG and vector search content
• You tend to bookmark practical tutorials and implementation guides

**Folder Organization:**
• AI Research: 8 items
• Development Tools: 6 items  
• Startup Resources: 5 items
• Uncategorized: 4 items

Your bookmarking pattern shows you're building knowledge systematically, focusing on actionable content you can apply to projects.`,
      results: mockResults,
      sources: ['Your bookmark folders'],
      queryType: 'search',
      metadata: {
        totalResults: mockResults.length,
        searchTime: 0.15,
        confidence: 0.97,
      },
    };
  }

  async getUserAnalysis(userId: string): Promise<UserAnalysis> {
    await this.delay(600);
    
    return {
      topTopics: [
        'Artificial Intelligence',
        'Machine Learning', 
        'Software Engineering',
        'Startup Strategy',
        'Web Development'
      ],
      readingStats: {
        totalItems: 127,
        bookmarks: 23,
        readingHistory: 104,
        thisWeek: 12,
        thisMonth: 47,
      },
      contentTypes: {
        'article': 68,
        'research_paper': 32,
        'youtube_video': 18,
        'podcast': 9,
      },
      readingPatterns: {
        avgReadingTime: 8.5,
        preferredContentLength: 'medium',
        peakReadingHours: [9, 10, 19, 20],
      },
      interests: [
        { topic: 'AI/ML', confidence: 0.95, trendDirection: 'increasing' },
        { topic: 'Software Engineering', confidence: 0.87, trendDirection: 'stable' },
        { topic: 'Startups', confidence: 0.72, trendDirection: 'increasing' },
        { topic: 'Web Development', confidence: 0.65, trendDirection: 'stable' },
      ],
    };
  }

  async searchContent(userId: string, query: string, filters?: any): Promise<ContentResult[]> {
    await this.delay(400);
    return this.mockSearchResponse({ message: query, userId }).then(r => r.results);
  }

  async getRecommendations(userId: string, limit = 5): Promise<ContentResult[]> {
    await this.delay(500);
    return this.mockRecommendationResponse({ message: 'recommend', userId }).then(r => r.results);
  }

  async findSimilarContent(userId: string, contentId: string, limit = 5): Promise<ContentResult[]> {
    await this.delay(350);
    return [{
      id: '7',
      title: 'Advanced RAG Techniques',
      type: 'article', 
      author: 'AI Engineering',
      aiSummary: 'Advanced techniques for improving RAG system performance and accuracy.',
      sourceUrl: 'https://example.com/advanced-rag',
      relevanceScore: 0.94,
    }];
  }
}

// Real implementation for Python FastAPI backend
class PythonChatService implements ChatAPI {
  private baseUrl = API_CONFIG.PYTHON_BACKEND_URL;

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Chat API error: ${response.statusText}`);
    }

    return response.json();
  }

  async getUserAnalysis(userId: string): Promise<UserAnalysis> {
    const response = await fetch(`${this.baseUrl}/api/users/${userId}/analysis`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
    });

    if (!response.ok) {
      throw new Error(`User analysis API error: ${response.statusText}`);
    }

    return response.json();
  }

  async searchContent(userId: string, query: string, filters?: any): Promise<ContentResult[]> {
    const params = new URLSearchParams({
      q: query,
      user_id: userId,
      ...filters,
    });

    const response = await fetch(`${this.baseUrl}/api/search?${params}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Search API error: ${response.statusText}`);
    }

    return response.json();
  }

  async getRecommendations(userId: string, limit = 5): Promise<ContentResult[]> {
    const response = await fetch(`${this.baseUrl}/api/users/${userId}/recommendations?limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Recommendations API error: ${response.statusText}`);
    }

    return response.json();
  }

  async findSimilarContent(userId: string, contentId: string, limit = 5): Promise<ContentResult[]> {
    const response = await fetch(`${this.baseUrl}/api/content/${contentId}/similar?user_id=${userId}&limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Similar content API error: ${response.statusText}`);
    }

    return response.json();
  }
}

// Export the service instance based on configuration
export const chatService: ChatAPI = API_CONFIG.USE_MOCK 
  ? new MockChatService() 
  : new PythonChatService();

// For debugging
console.log(`🤖 Chat Service: ${API_CONFIG.USE_MOCK ? 'Mock' : 'Python Backend'} (${API_CONFIG.PYTHON_BACKEND_URL})`);