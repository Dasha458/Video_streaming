import clientApi from "./clientApi";
import type { VideoPreview } from "./types";
import { mapToPreview } from "./videoApi";

interface LikedPage {
  items: any[];
  page: number;
  size: number;
  total: number;
}

export const getLikedVideos = (
  page: number = 1,
  size: number = 20,
): Promise<{ items: VideoPreview[]; total: number }> =>
  clientApi
    .get<LikedPage>("/api/liked", { params: { page, size } })
    .then((res) => ({
      items: res.data.items.map(mapToPreview),
      total: res.data.total,
    }));

export default { getLikedVideos };
