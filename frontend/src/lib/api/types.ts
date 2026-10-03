/** Mirrors backend src/schemas/channel.py's ChannelResponse exactly --
 * that schema itself carries both a snake_case DB-shaped field set
 * (avatar_path, subscribers_count, created_at, ...) and a second
 * camelCase set (channel_avatar, subscribersCount, createdAt, ...) for
 * frontend convenience. Both are real and present on every response;
 * this is not duplication introduced here. */
/** Backend src/schemas/channel.py's ChannelResponse.
 *
 *  It used to declare eighteen fields for six pieces of information,
 *  because the server sent every value twice under two conventions and
 *  nothing said which one would arrive -- so call sites read
 *  `subscribersCount ?? subscribers_count ?? 0`. One name per value now. */
export interface ChannelInfo {
  id: string;
  name: string;
  description?: string | null;
  subscribers_count: number;
  views_count: number;
  videos_count: number;
  avatar_path?: string | null;
  background_path?: string | null;
  created_at: string;
  is_owner: boolean;
  is_subscribed: boolean;
}

/** Backend src/schemas/channel.py's ChannelSubscriptionItem -- the actual
 * (smaller) shape GET /api/channels/subscriptions returns. Previously
 * mistyped as ChannelInfo[], which claims several required fields
 * (id, isOwner, avatar_path, ...) this endpoint never sends. */
export interface ChannelSubscriptionItem {
  name: string;
  avatar_path?: string | null;
  subscribers_count: number;
  videos_count: number;
  created_at: string;
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

export interface Playlist {
  id: string;
  title: string;
  description?: string;
  createdAt: string;
  updatedAt?: string;
  videoIds: string[];
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
/** Backend src/api/changelog.py. Built from the repository's commit history
 *  by utils/build_changelog.py -- there are no tags in this project, so
 *  entries are months rather than versions. */
export interface ChangelogEntry {
  period: string;
  date: string;
  new_features?: string[];
  improvements?: string[];
  bugfixes?: string[];
  tags?: string[];
  other_changes?: number;
}
export interface Category {
  id: string;
  name: string;
}

interface StoredFile {
  file_id: string;
  filename: string;
  size: number;
}

export interface UploadResponse {
  status: string;
  files?: StoredFile[];
  message?: string;
}

export interface DownloadResponse {
  status: string;
  files: StoredFile[];
  message?: string;
}

/** Exactly what POST /api/videos/{id}/reactions returns (schemas/reaction.py).
 *  It used to also declare likesCount/dislikesCount, which the server never
 *  sends -- callers reading them got undefined while TypeScript said number. */
export interface ReactionResponse {
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
}

export interface NoSearchResultsProps {
  query: string;
}

export interface SearchHintsResponse {
  hints: string[];
}
