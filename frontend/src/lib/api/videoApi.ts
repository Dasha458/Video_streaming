import { AxiosError } from "axios";
import clientApi from "./clientApi";
import { getVisitorId, VISITOR_HEADER } from "@/lib/visitorId";
import { timeAgo } from "@/utils/timeAgo";
import type {
  Video,
  VideoPreview,

  DownloadResponse,
} from "./types";

/** Shape of backend src/schemas/video.py's VideoPreview -- what the API
 * actually returns for listing endpoints, before mapToPreview reshapes it
 * into the frontend's VideoPreview. */
export interface RawVideoPreview {
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

/** `source` is the traffic-source hint the backend stamps on the VideoView
 *  row this request creates. Omitting it recorded every view as "unknown". */
export const getVideo = async (id: string, source?: string): Promise<Video> => {
  const res = await clientApi.get<RawVideoPlayback>(`/api/videos/${id}`, {
    params: source ? { source } : undefined,
    // This request is what records a view, and a view is one viewer, so it
    // has to say which viewer. Signed-in callers are identified by their
    // session; this covers everyone else.
    headers: { [VISITOR_HEADER]: getVisitorId() },
  });
  return mapToDetail(res.data);
};

export interface StreamUrl {
  url: string;
  expires_in: number;
}

/** Where the player should load this video from.
 *
 *  The server checks the video's privacy against the caller before
 *  answering, and refuses with a 404 when they may not watch it. This is
 *  the only way to obtain a media URL: the endpoint that used to sign any
 *  path it was handed is gone. */
export const getStreamUrl = (videoId: string): Promise<StreamUrl> =>
  clientApi
    .get<StreamUrl>(`/api/videos/${videoId}/stream-url`)
    .then((res) => res.data);

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

/** The one MP4 the converter prepared for this video.
 *
 *  The resolution parameter is gone: asking for one returned the HLS
 *  playlist with a .mp4 name. The error is no longer replaced with a
 *  fixed string either -- the server explains whether the video is still
 *  encoding or has no downloadable file, and the caller showed "Failed to
 *  download video" over the top of it. */
export const downloadVideo = async (videoId: string): Promise<Blob> => {
  try {
    const res = await clientApi.get(`/api/files/videos/${videoId}/download`, {
      responseType: "blob",
    });
    return res.data;
  } catch (err) {
    // responseType "blob" applies to failures too, so the error body
    // arrives as a Blob and every reader of response.data.message sees
    // undefined. Decoding it here keeps the explanation the server sent.
    const body = (err as AxiosError)?.response?.data;
    if (body instanceof Blob) {
      try {
        (err as AxiosError).response!.data = JSON.parse(await body.text());
      } catch {
        // Not JSON -- leave it alone and let the caller's fallback show.
      }
    }
    throw err;
  }
};

export default {
  getVideos,
  getVideo,
  getStreamUrl,
  updateVideoPrivacy,
  deleteVideo,
  downloadVideo,
  getVideoDownloadInfo,
  getVideoPreviewsByCategory,
};
