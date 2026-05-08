import clientApi from "./clientApi";
import type { VideoPreview } from "./types";

interface WatchLaterItem {
  id: string;
  title: string;
  thumbnail: string;
  channel_name: string;
  channel_avatar: string;
  views_count: number;
  created_at: string;
  added_at: string;
}

interface WatchLaterPage {
  items: WatchLaterItem[];
  page: number;
  size: number;
  total: number;
}

const mapItem = (item: WatchLaterItem): VideoPreview => ({
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

export const getWatchLater = (
  page: number = 1,
  size: number = 20,
): Promise<{ items: VideoPreview[]; total: number }> =>
  clientApi
    .get<WatchLaterPage>("/api/watch-later", { params: { page, size } })
    .then((res) => ({
      items: res.data.items.map(mapItem),
      total: res.data.total,
    }));

export const addToWatchLater = (videoId: string): Promise<void> =>
  clientApi.post(`/api/watch-later/${videoId}`).then(() => {});

export const removeFromWatchLater = (videoId: string): Promise<void> =>
  clientApi.delete(`/api/watch-later/${videoId}`).then(() => {});

export const clearWatchLater = (): Promise<void> =>
  clientApi.delete("/api/watch-later").then(() => {});

export default { getWatchLater, addToWatchLater, removeFromWatchLater, clearWatchLater };
