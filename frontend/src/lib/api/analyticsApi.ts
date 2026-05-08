import clientApi from "./clientApi";

// ── Common ─────────────────────────────────────────────────────────────────

export type Period = "7d" | "28d" | "90d" | "365d" | "all";

export interface DailyMetric {
  date: string; // YYYY-MM-DD
  count: number;
}

export interface HourlyMetric {
  hour: string; // ISO-8601 with :00:00
  count: number;
}

export interface DeltaInt {
  value: number;
  previous: number;
  delta_percent: number;
}

// ── Overview ───────────────────────────────────────────────────────────────

export interface TopVideo {
  id: string;
  title: string;
  thumbnail: string;
  views_count: number;
  likes_count: number;
  comments_count: number;
}

export interface OverviewData {
  period: Period;
  total_views: DeltaInt;
  total_subscribers: number;
  total_likes: DeltaInt;
  total_comments: DeltaInt;
  total_watch_time_seconds: DeltaInt;
  views_per_day: DailyMetric[];
  top_videos: TopVideo[];
}

// ── Content ────────────────────────────────────────────────────────────────

export interface VideoStat {
  id: string;
  title: string;
  thumbnail: string;
  privacy: "public" | "private";
  views_count: number;
  likes_count: number;
  dislikes_count: number;
  comments_count: number;
  created_at: string;
}

export interface ContentData {
  period: Period;
  videos: VideoStat[];
}

// ── Audience ───────────────────────────────────────────────────────────────

export interface AudienceData {
  period: Period;
  subscribers_per_day: DailyMetric[];
  unique_viewers: number;
  returning_viewers: number;
  comments_per_day: DailyMetric[];
}

// ── Engagement ─────────────────────────────────────────────────────────────

export interface EngagementData {
  period: Period;
  total_watch_time_seconds: number;
  average_view_duration_seconds: number;
  average_percent_viewed: number;
  engagement_rate: number;
  watch_time_per_day: DailyMetric[];
  avg_percent_viewed_per_day: DailyMetric[];
}

// ── Real-time ──────────────────────────────────────────────────────────────

export interface RealtimeData {
  views_last_48h: number;
  views_last_60min: number;
  views_per_hour: HourlyMetric[];
  top_videos_48h: TopVideo[];
}

// ── Traffic sources ────────────────────────────────────────────────────────

export interface TrafficSourceSlice {
  source: string;
  views: number;
  percentage: number;
}

export interface TrafficSourcesData {
  period: Period;
  total_views: number;
  sources: TrafficSourceSlice[];
}

// ── Per-video ──────────────────────────────────────────────────────────────

export interface RetentionBucket {
  percent: number;
  viewers: number;
}

export interface VideoAnalyticsData {
  video_id: string;
  title: string;
  thumbnail: string;
  period: Period;
  views: DeltaInt;
  likes: DeltaInt;
  dislikes: DeltaInt;
  comments: DeltaInt;
  watch_time_seconds: DeltaInt;
  average_view_duration_seconds: number;
  average_percent_viewed: number;
  views_per_day: DailyMetric[];
  retention: RetentionBucket[];
  traffic_sources: TrafficSourceSlice[];
}

// ── Watch session heartbeat ────────────────────────────────────────────────

export interface WatchSessionPing {
  session_id: string; // UUID v4 generated on client
  video_id: string;
  watched_seconds: number;
  video_duration_seconds: number;
  source_type?: string;
}

export interface WatchSessionAck {
  ok: boolean;
  session_id: string;
  completed_percent: number;
}

// ── API calls ──────────────────────────────────────────────────────────────

const q = (period?: Period) =>
  period ? { params: { period } } : undefined;

export const getOverview = (period: Period = "28d"): Promise<OverviewData> =>
  clientApi.get<OverviewData>("/api/analytics/overview", q(period)).then((r) => r.data);

export const getContent = (period: Period = "28d"): Promise<ContentData> =>
  clientApi.get<ContentData>("/api/analytics/content", q(period)).then((r) => r.data);

export const getAudience = (period: Period = "28d"): Promise<AudienceData> =>
  clientApi.get<AudienceData>("/api/analytics/audience", q(period)).then((r) => r.data);

export const getEngagement = (period: Period = "28d"): Promise<EngagementData> =>
  clientApi.get<EngagementData>("/api/analytics/engagement", q(period)).then((r) => r.data);

export const getRealtime = (): Promise<RealtimeData> =>
  clientApi.get<RealtimeData>("/api/analytics/realtime").then((r) => r.data);

export const getTrafficSources = (
  period: Period = "28d",
): Promise<TrafficSourcesData> =>
  clientApi
    .get<TrafficSourcesData>("/api/analytics/traffic-sources", q(period))
    .then((r) => r.data);

export const getVideoAnalytics = (
  videoId: string,
  period: Period = "28d",
): Promise<VideoAnalyticsData> =>
  clientApi
    .get<VideoAnalyticsData>(`/api/analytics/videos/${videoId}`, q(period))
    .then((r) => r.data);

export const sendWatchSession = (
  ping: WatchSessionPing,
): Promise<WatchSessionAck> =>
  clientApi
    .post<WatchSessionAck>("/api/analytics/watch-session", ping)
    .then((r) => r.data);

/** Fire-and-forget final ping on tab close using sendBeacon. */
export const beaconWatchSession = (ping: WatchSessionPing): boolean => {
  try {
    const token = localStorage.getItem("token");
    // sendBeacon does not honour custom headers → fall back to fetch with keepalive
    // when we need the Bearer header.
    if (token) {
      return navigator
        .sendBeacon(
          "/api/analytics/watch-session",
          new Blob([JSON.stringify(ping)], { type: "application/json" }),
        );
    }
    return navigator.sendBeacon(
      "/api/analytics/watch-session",
      new Blob([JSON.stringify(ping)], { type: "application/json" }),
    );
  } catch {
    return false;
  }
};
