import { useCallback } from "react";

import { useToast } from "@/components/ui/toast/use-toast";
import { getApiErrorMessage } from "@/utils/apiError";
import { downloadVideo } from "@api/videoApi";
import type { VideoDetail } from "@api/types";

interface UseDownloadProps {
  video: VideoDetail | null;
}

/** Fetches the single MP4 the converter built for this video.
 *
 *  There is no resolution to choose any more: asking for one returned an
 *  HLS playlist saved under a .mp4 name. */
export function useDownload({ video }: UseDownloadProps) {
  const { toast } = useToast();

  const handleDownload = useCallback(async () => {
    if (!video?.id) {
      toast({
        title: "Cannot download: Video is missing.",
        variant: "destructive",
      });
      return;
    }

    try {
      toast({ title: "Preparing download..." });

      const blob = await downloadVideo(video.id);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;

      // Strip characters Windows/macOS reject in a filename.
      const safeTitle = (video.title || "video").replace(/[\\/:*?"<>|]+/g, "_");
      a.download = `${safeTitle}.mp4`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoking in the same tick can abort the transfer the click just
      // started; let the browser pick the blob up first.
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);

      toast({ title: "Download started" });
    } catch (error) {
      console.error("Download failed:", error);
      toast({
        title: getApiErrorMessage(error, "Download failed"),
        variant: "destructive",
      });
    }
  }, [video, toast]);

  return { handleDownload };
}
