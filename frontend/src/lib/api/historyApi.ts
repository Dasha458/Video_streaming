import clientApi from "./clientApi";
import type { VideoPreview } from "./types";

interface HistoryItem {
  id: string;
  title: string;
  thumbnail: string;
  channel_name: string;
  channel_avatar: string;
  views_count: number;
  created_at: string;
  last_watched_at: string;
}

interface HistoryPage {
  items: HistoryItem[];
  page: number;
  size: number;
  total: number;
}

const mapHistoryItem = (item: HistoryItem): VideoPreview => ({
  id: item.id,
  title: item.title,
  previewUrl: item.thumbnail || "/placeholder.jpg",
  channel_avatar: item.channel_avatar || "",
  channel: item.channel_name || "",
  channel_name: item.channel_name || "",
  views: item.views_count ?? 0,
  createdAt: item.created_at || new Date().toISOString(),
  publishedAt: item.created_at || new Date().toISOString(),
  likesCount: 0,
  dislikesCount: 0,
  privacy: "Public",
});

export const getUserHistory = (
  page: number = 1,
  size: number = 20,
): Promise<{ items: VideoPreview[]; total: number }> =>
  clientApi
    .get<HistoryPage>(`/api/history`, { params: { page, size } })
    .then((res) => ({
      items: res.data.items.map(mapHistoryItem),
      total: res.data.total,
    }));

export const clearUserHistory = (): Promise<void> =>
  clientApi.delete("/api/history").then(() => {});

export const removeVideoFromHistory = (videoId: string): Promise<void> =>
  clientApi.delete(`/api/history/${videoId}`).then(() => {});

export default { getUserHistory, clearUserHistory, removeVideoFromHistory };
