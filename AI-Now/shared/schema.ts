export type User = {
  id: string;
  email: string;
  firstName: string | null;
  lastName: string | null;
  interests: string;
  onboardingCompleted: boolean;
  createdAt: string;
  updatedAt: string;
};

export type ContentItem = {
  id: string;
  title: string;
  sourceUrl?: string;
  thumbnailUrl?: string;
  type: 'youtube_video' | 'podcast' | 'research_paper' | 'academic' | 'twitter_post' | 'article';
  aiSummary?: string;
  author?: string;
  publishedAt?: string;
}; 