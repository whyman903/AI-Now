export type ContentItem = {
  id: string;
  title: string;
  sourceUrl?: string;
  thumbnailUrl?: string;
  type: string;
  aiSummary?: string;
  author?: string;
  publishedAt?: string;
  metadata?: Record<string, any> | null;
};
