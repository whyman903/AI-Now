export type ContentItem = {
  id: string;
  title: string;
  sourceUrl?: string | null;
  thumbnailUrl?: string | null;
  type: string;
  aiSummary?: string;
  author?: string | null;
  publishedAt?: string | null;
  metadata?: Record<string, any> | null;
};
