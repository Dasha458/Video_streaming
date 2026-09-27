import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/ui/toast/use-toast";
import { getApiErrorMessage } from "@/utils/apiError";
import reactionApi from "@api/reactionApi";
import type { VideoDetail } from "@api/types";

type ReactionType = "like" | "dislike";
type UserReactionState = ReactionType | null;

interface UseReactionsProps {
  initialVideo: VideoDetail | null;
  initialUserReaction: UserReactionState;
  onVideoUpdate: (newVideo: VideoDetail) => void;
}

interface UseReactionsResult {
  userReaction: UserReactionState;
  handleReaction: (reactionType: ReactionType) => Promise<void>;
  isPending: boolean;
}

export function useReactions({
  initialVideo,
  initialUserReaction,
  onVideoUpdate,
}: UseReactionsProps): UseReactionsResult {
  const [userReaction, setUserReaction] = useState(initialUserReaction);
  const [isPending, setIsPending] = useState(false);
  // A ref as well as state: two clicks in the same tick would both read the
  // pre-render `isPending === false` and fire two requests, each computing
  // from the same stale counts.
  const inFlightRef = useRef(false);
  const { toast } = useToast();

  useEffect(() => {
    setUserReaction(initialUserReaction);
  }, [initialUserReaction]);

  const handleReaction = useCallback(
    async (reactionType: ReactionType) => {
      if (!initialVideo || inFlightRef.current) return;

      inFlightRef.current = true;
      setIsPending(true);

      const prevReaction = userReaction;
      const currentLikes = initialVideo.likesCount;
      const currentDislikes = initialVideo.dislikesCount;

      let newLikes = currentLikes;
      let newDislikes = currentDislikes;
      let nextReaction: UserReactionState;

      if (prevReaction === reactionType) {
        nextReaction = null;
        if (reactionType === "like") newLikes = Math.max(0, currentLikes - 1);
        else newDislikes = Math.max(0, currentDislikes - 1);
      } else {
        nextReaction = reactionType;
        if (reactionType === "like") {
          newLikes += 1;
          if (prevReaction === "dislike")
            newDislikes = Math.max(0, currentDislikes - 1);
        } else {
          newDislikes += 1;
          if (prevReaction === "like") newLikes = Math.max(0, currentLikes - 1);
        }
      }

      const newVideoData: VideoDetail = {
        ...initialVideo,
        likesCount: newLikes,
        dislikesCount: newDislikes,
        userReaction: nextReaction,
      };

      onVideoUpdate(newVideoData);
      setUserReaction(nextReaction);

      try {
        // Reconcile with the server's own counts instead of trusting the
        // optimistic arithmetic -- that is what keeps the UI from drifting.
        const { reactions } = await reactionApi.sendReaction(
          initialVideo.id,
          reactionType,
        );
        onVideoUpdate({
          ...newVideoData,
          likesCount: reactions.like ?? newLikes,
          dislikesCount: reactions.dislike ?? newDislikes,
        });
      } catch (error) {
        console.error("Error sending reaction:", error);
        toast({
          title: getApiErrorMessage(error, "Could not save the reaction"),
          variant: "destructive",
        });
        onVideoUpdate(initialVideo);
        setUserReaction(prevReaction);
      } finally {
        inFlightRef.current = false;
        setIsPending(false);
      }
    },
    [initialVideo, userReaction, onVideoUpdate, toast],
  );

  return { userReaction, handleReaction, isPending };
}
