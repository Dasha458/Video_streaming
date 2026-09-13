/** Mirrors backend src/schemas/channel.py's ChannelResponse exactly --
 * that schema itself carries both a snake_case DB-shaped field set
 * (avatar_path, subscribers_count, created_at, ...) and a second
 * camelCase set (channel_avatar, subscribersCount, createdAt, ...) for
 * frontend convenience. Both are real and present on every response;
 * this is not duplication introduced here. */
export interface ChannelInfo {
  id: string;
  name: string;
  description?: string | null;
  subscribers_count: number;
  views_count: number;
  avatar_path?: string | null;
  background_path?: string | null;
  created_at: string;
  isOwner: boolean;
  isSubscribed: boolean;
  channel_name: string;
  channel_avatar: string;
  channelBanner?: string;
  subscribersCount: number;
  videosCount: number;
  bio?: string;
  createdAt: string;
}

/** Backend src/schemas/channel.py's ChannelSubscriptionItem -- the actual
 * (smaller) shape GET /api/channels/subscriptions returns. Previously
 * mistyped as ChannelInfo[], which claims several required fields
 * (id, isOwner, avatar_path, ...) this endpoint never sends. */
export interface ChannelSubscriptionItem {
  channel_name: string;
  channel_avatar?: string | null;
  subscribersCount: number;
  videosCount: number;
  createdAt: string;
}

export interface VideoPreview {
  name?: string;
  thumbnail_url?: string;
  channel_name?: string;
  id: string;
  title: string;
  previewUrl: string;
  channel_avatar: string;
  createdAt: string;
  channel: string;
  views: number;
  likesCount: number;
  publishedAt: string;
  dislikesCount: number;
  privacy: string;
  status?: string;
  // Not returned by any video-listing endpoint today (GET /api/videos/,
  // /api/videos/categories/{category}) -- always undefined in practice.
  // A real per-video comment count would need a backend change; kept
  // optional here so call sites read it honestly instead of casting.
  commentCount?: number;
}

export interface Video {
  id: string;
  title: string;
  name: string;
  avatar_url?: string;
  master_hls_url: string;
  thumbnail_url: string;
  created_at: string;
  views_count: number;
  likes_count: number;
  dislikes_count: number;
  privacy: string;
  category?: string;
  channel_avatar?: string;
  channel_name: string;
  status: "Processing" | "Ready" | "Failed";
  comments?: VideoComment[];
  commentCount?: number;
  preview_url?: string;
  description?: string;
  timeAgo?: string;
  // publishedAt/size/hash/channelId removed: GET /api/videos/{id} (VideoPlayback,
  // see videoApi.ts's RawVideoPlayback) never returns these, and nothing in the
  // frontend reads them off a Video value -- they were required here but always
  // absent in practice.
}

export interface VideoComment {
  id: string;
  userId: string;
  content: string;
  createdAt: string;
  // Not present on backend src/schemas/comments.py's CommentRead -- comments
  // are only ever fetched already scoped to a video, so it's never echoed
  // back. Kept optional (never actually set) rather than removed outright.
  videoId?: string;
  parentId?: string;
  likesCount: number;
  dislikesCount: number;
  user_name?: string;
  user_avatar?: string;
  replies?: VideoComment[];
}

export interface UserInfo {
  id: string;
  username: string;
  email: string;
  created_at?: string;
  is_active?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
}

export interface ChannelPreview {
  channel_name: string;
  channel_avatar: string;
  subscribersCount: number;
  videosCount: number;
}

export interface Playlist {
  id: string;
  title: string;
  description?: string;
  createdAt: string;
  updatedAt?: string;
  videoIds: string[];
  isPublic: boolean;
}

export interface PlaylistPreview {
  id: string;
  title: string;
  videoCount: number;
  createdAt: string;
  isPublic: boolean;
}

export interface Notification {
  id: string;
  userId: string;
  type: "new_video" | "new_subscriber" | "comment_reply" | "like" | "dislike";
  content: string;
  isRead: boolean;
  createdAt: string;
  relatedEntityId?: string;
}
export interface ChangelogEntry {
  date: string;
  version: string;
  improvements?: string[];
  bugfixes?: string[];
  newFeatures?: string[];
  imageUrl?: string;
  tags?: string[];
}
export interface Category {
  id: string;
  name: string;
}

export interface UploadedFile {
  file_id: string;
  filename: string;
  size: number;
}

export interface UploadResponse {
  status: string;
  files?: UploadedFile[];
  message?: string;
}

export interface DownloadVideo {
  file_id: string;
  filename: string;
  size: number;
}

export interface DownloadResponse {
  status: string;
  files: DownloadVideo[];
  message?: string;
}

export interface ReactionResponse {
  likesCount: number;
  dislikesCount: number;
  target_id: string;
  target_type: string;
  reactions: {
    like: number;
    dislike: number;
    [key: string]: number;
  };
}

export type VideoDetail = VideoPreview & {
  timeAgo?: string;
  description: string;
  hlsUrl: string;
  likesCount: number;
  dislikeCount: number;
  userReaction: "like" | "dislike" | null;
};

export type VideoPreviewWithTime = VideoPreview & {
  timeAgo: string;
};

export interface SearchFilters {
  category?: string;
  minViews?: number; // Minimum view count
  maxViews?: number; // Maximum view count
  includeDescription: boolean; // Also match the video description, not just the title
  smartSearch: boolean;
}

export interface SearchResponse {
  results: VideoPreview[];
}
type SetVideoState = React.Dispatch<React.SetStateAction<VideoDetail | null>>;
export interface UseVideoResult {
  // --- Data ---
  video: VideoDetail | null;
  videos: VideoPreviewWithTime[];
  comments: VideoComment[];
  error: string | null;
  loading: boolean;
  hasMore: boolean;
  page: number; // Current page for pagination
  setVideo: SetVideoState;
  // --- Actions consumers call ---
  loadMore: () => Promise<void>;
  loadMoreSearchResults: () => Promise<void>;
  formatViews: (views: number | undefined) => string;
  metaDataText: string;

  // --- Raw setters for advanced consumers ---
  setVideos: React.Dispatch<React.SetStateAction<VideoPreviewWithTime[]>>;
  setPage: React.Dispatch<React.SetStateAction<number>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setHasMore: React.Dispatch<React.SetStateAction<boolean>>;

  // --- Search state ---
  searchQuery: string; // Current search query text
  setSearchQuery: React.Dispatch<React.SetStateAction<string>>;
  setSearchFilters: React.Dispatch<
    React.SetStateAction<SearchFilters | undefined>
  >;
}

export interface NoSearchResultsProps {
  query: string;
}
export interface SearchApiResponse {
  results: VideoPreview[];
}
export interface SearchHintsResponse {
  hints: string[];
}
