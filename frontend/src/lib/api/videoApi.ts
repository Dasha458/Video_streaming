import { AxiosError } from "axios";
import clientApi from "./clientApi";
import { timeAgo } from "@/utils/timeAgo";
import type {
  Video,
  VideoPreview,
  UploadResponse,
  DownloadResponse,
} from "./types";

/** Shape of backend src/schemas/video.py's VideoPreview -- what the API
 * actually returns for listing endpoints, before mapToPreview reshapes it
 * into the frontend's VideoPreview. */
interface RawVideoPreview {
  id: string;
  title: string;
  thumbnail: string;
  channel_avatar: string;
  channel_name: string;
  views_count: number;
  likes_count: number;
  dislikes_count: number;
  privacy: string;
  status: string;
  created_at: string;
}

/** Shape of backend src/schemas/video.py's VideoPlayback -- what
 * GET /api/videos/{id} actually returns, before mapToDetail reshapes it. */
interface RawVideoPlayback {
  id: string;
  name: string;
  description?: string | null;
  privacy: string;
  created_at: string;
  resolutions: string[];
  thumbnail_url?: string | null;
  avatar_url?: string | null;
  channel_name: string;
  likes_count: number;
  dislikes_count: number;
  views_count: number;
  master_hls_url?: string | null;
}

interface VideosResponse {
  items: RawVideoPreview[];
  page: number;
  size: number;
  total: number;
}

export const mapToPreview = (data: RawVideoPreview): VideoPreview => ({
  id: data.id,
  previewUrl: data.thumbnail || "/placeholder.jpg",
  thumbnail_url: data.thumbnail || "/placeholder.jpg",
  title: data.title || "Untitled",
  name: data.title || "Untitled",
  createdAt: data.created_at || new Date().toISOString(),
  publishedAt: data.created_at || new Date().toISOString(),
  channel: data.channel_name || "Unknown Channel",
  channel_name: data.channel_name || "Unknown Channel",
  channel_avatar: data.channel_avatar || "",
  views: data.views_count ?? 0,
  likesCount: data.likes_count ?? 0,
  dislikesCount: data.dislikes_count ?? 0,
  privacy: data.privacy ?? "public",
  status: data.status ?? "Ready",
});

export const mapToDetail = (data: RawVideoPlayback): Video => ({
  id: data.id,
  description: data.description ?? undefined,
  preview_url: data.thumbnail_url || "/placeholder.jpg",
  thumbnail_url: data.thumbnail_url || "/placeholder.jpg",
  master_hls_url: data.master_hls_url || "",
  created_at: data.created_at || "",
  timeAgo: timeAgo(data.created_at || new Date().toISOString()),
  channel_avatar: data.avatar_url || "",
  likes_count: data.likes_count ?? 0,
  dislikes_count: data.dislikes_count ?? 0,
  views_count: data.views_count ?? 0,
  channel_name: data.channel_name || "Unknown Channel",
  name: data.name || "Untitled",
  title: data.name || "Untitled",
  privacy: data.privacy === "public" ? "Public" : "Private",
  status: "Ready",
});

export const getVideos = async ({
  page = 1,
  size = 10,
  channel_name,
}: {
  page?: number;
  size?: number;
  channel_name?: string;
}): Promise<VideoPreview[]> => {
  const res = await clientApi.get<VideosResponse>("/api/videos/", {
    params: { page, size, channel_name },
  });
  return (res.data.items || []).map(mapToPreview);
};

export const getVideo = async (id: string): Promise<Video> => {
  const res = await clientApi.get<RawVideoPlayback>(`/api/videos/${id}`);
  return mapToDetail(res.data);
};

export const getVideoPreviewsByCategory = async (
  category: string,
  page = 1,
  size = 10,
): Promise<VideoPreview[]> => {
  const res = await clientApi.get<VideosResponse>(
    `/api/videos/categories/${category}`,
    { params: { page, size } },
  );
  return (res.data.items || []).map(mapToPreview);
};

export const uploadVideo = async (
  file: File,
  options?: {
    title?: string;
    description?: string;
    thumbnail?: File;
    isPublic?: boolean;
    category?: string;
  },
): Promise<UploadResponse> => {
  try {
    // Everything goes in the multipart body: a title or description in the
    // query string would be recorded in the gateway's access log.
    const formData = new FormData();
    formData.append("video", file);
    if (options?.thumbnail) formData.append("thumbnail", options.thumbnail);
    formData.append("name", options?.title || "Untitled");
    formData.append("description", options?.description || "");
    formData.append("privacy", options?.isPublic ? "public" : "private");
    formData.append("category", options?.category || "entertainment");

    const res = await clientApi.post<UploadResponse>(
      `/api/files/videos`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );

    return res.data;
  } catch (err) {
    const axiosErr = err as AxiosError<{ message?: string }>;
    return Promise.reject(axiosErr.response?.data || { message: "Upload failed" });
  }
};

export const deleteVideo = async (id: string): Promise<void> => {
  await clientApi.delete(`/api/files/videos/${id}`);
};

interface PrivacyUpdateResponse {
  video_id: string;
  old_privacy: string;
  updated_privacy: string;
}

export const updateVideoPrivacy = async (
  id: string,
  isPublic: boolean,
): Promise<PrivacyUpdateResponse> => {
  const res = await clientApi.patch<PrivacyUpdateResponse>(`/api/videos/${id}/privacy`, null, {
    params: { updated_privacy: isPublic ? "public" : "private" },
  });
  return res.data;
};

export const getVideoDownloadInfo = async (
  videoId: string,
): Promise<DownloadResponse> => {
  const res = await clientApi.get<DownloadResponse>(
    `/api/files/videos/${videoId}/download`,
  );
  return res.data;
};

export const downloadVideo = async (
  videoId: string,
  resolution = "720p",
): Promise<Blob> => {
  try {
    const res = await clientApi.get(`/api/files/videos/${videoId}/download`, {
      params: { resolution },
      responseType: "blob",
    });
    return res.data;
  } catch (err) {
    console.error("Download error:", err);
    return Promise.reject({ message: "Failed to download video" });
  }
};

export default {
  getVideos,
  getVideo,
  uploadVideo,
  updateVideoPrivacy,
  deleteVideo,
  downloadVideo,
  getVideoDownloadInfo,
  getVideoPreviewsByCategory,
};
