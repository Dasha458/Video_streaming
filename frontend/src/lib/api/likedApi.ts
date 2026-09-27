import clientApi from "./clientApi";
import type { VideoPreview } from "./types";
import { mapToPreview, type RawVideoPreview } from "./videoApi";

interface LikedPage {
  /** Same rows the listing endpoints return -- mapToPreview reshapes them.
   *  This was `any[]`, so nothing checked that the two agreed. */
  items: RawVideoPreview[];
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
