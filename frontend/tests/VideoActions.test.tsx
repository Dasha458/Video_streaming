import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "./utils";

vi.mock("@/hooks/useDownload", () => ({
    useDownload: () => ({ handleDownload: vi.fn() }),
}));
vi.mock("@/hooks/useReactions", () => ({
    useReactions: () => ({ handleReaction: vi.fn() }),
}));
vi.mock("@/pages/Watch/PlaylistMenu", () => ({
    PlaylistMenu: () => null,
}));
vi.mock("@api/watchLaterApi", () => ({ addToWatchLater: vi.fn() }));

import { VideoActions } from "../src/pages/Watch/VideoActions";

const video = (isOwner: boolean) =>
    ({
        id: "v1",
        title: "A clip",
        likesCount: 1,
        dislikesCount: 0,
        isOwner,
    }) as never;

describe("VideoActions — who is offered the download", () => {
    it("offers it to the uploader", () => {
        renderWithProviders(
            <VideoActions
                video={video(true)}
                videoId="v1"
                isSignedIn
                onVideoUpdate={vi.fn()}
            />,
        );

        expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
    });

    it("does not offer it to anybody else", () => {
        // It used to be shown to every viewer and refused by the server,
        // so the only way to find out was to click it.
        renderWithProviders(
            <VideoActions
                video={video(false)}
                videoId="v1"
                isSignedIn
                onVideoUpdate={vi.fn()}
            />,
        );

        expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
    });

    it("no longer asks which resolution to download", () => {
        // The choice could only ever fetch an HLS playlist saved as .mp4.
        renderWithProviders(
            <VideoActions
                video={video(true)}
                videoId="v1"
                isSignedIn
                onVideoUpdate={vi.fn()}
            />,
        );

        expect(screen.queryByLabelText(/resolution/i)).toBeNull();
        expect(screen.queryByRole("combobox")).toBeNull();
    });
});
