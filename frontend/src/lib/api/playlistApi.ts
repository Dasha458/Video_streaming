import clientApi from "./clientApi";
import type { VideoPreview } from "./types";
import { mapToPreview } from "./videoApi";

export interface PlaylistItem {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  video_count: number;
}

export interface PlaylistDetail {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  items: VideoPreview[];
  total: number;
}

export interface PlaylistsPage {
  items: PlaylistItem[];
  total: number;
}

export const getPlaylists = (): Promise<PlaylistsPage> =>
  clientApi.get<PlaylistsPage>("/api/playlists").then((res) => res.data);

export const createPlaylist = (
  name: string,
  description?: string,
): Promise<PlaylistItem> =>
  clientApi
    .post<PlaylistItem>("/api/playlists", { name, description })
    .then((res) => res.data);

export const getPlaylist = (playlistId: string): Promise<PlaylistDetail> =>
  clientApi
    .get<any>(`/api/playlists/${playlistId}`)
    .then((res) => ({
      ...res.data,
      items: (res.data.items ?? []).map(mapToPreview),
    }));

export const deletePlaylist = (playlistId: string): Promise<void> =>
  clientApi.delete(`/api/playlists/${playlistId}`).then(() => {});

export const addToPlaylist = (
  playlistId: string,
  videoId: string,
): Promise<void> =>
  clientApi
    .post(`/api/playlists/${playlistId}/videos`, null, { params: { video_id: videoId } })
    .then(() => {});

export const deleteFromPlaylist = (
  playlistId: string,
  videoId: string,
): Promise<void> =>
  clientApi
    .delete(`/api/playlists/${playlistId}/videos/${videoId}`)
    .then(() => {});

export default {
  getPlaylists,
  createPlaylist,
  getPlaylist,
  deletePlaylist,
  addToPlaylist,
  deleteFromPlaylist,
};
