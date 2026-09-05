const API_BASE = "http://localhost:8010";

export interface SampleArticle {
  id: string;
  preview: string;
  cluster_id: number;
}

export interface Article {
  id: string;
  text: string;
  cluster_id: number | null;
  source: string;
}

export interface Evidence {
  id: string;
  similarity: number;
  score: number | null;
}

export interface InvestigateResult {
  model_available: boolean;
  message?: string;
  aggregated_score?: number;
  single_instance_score?: number;
  evidence: Evidence[];
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export function fetchSampleArticles(limit = 12) {
  return getJSON<SampleArticle[]>(`/api/articles/sample?limit=${limit}`);
}

export function fetchArticle(id: string) {
  return getJSON<Article>(`/api/articles/${encodeURIComponent(id)}`);
}

export async function investigate(text: string, articleId: string, k = 6): Promise<InvestigateResult> {
  const res = await fetch(`${API_BASE}/api/investigate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, article_id: articleId, k }),
  });
  if (!res.ok) throw new Error(`investigate -> ${res.status}`);
  return res.json();
}
