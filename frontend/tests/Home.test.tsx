import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "../src/pages/Home";
import { renderWithProviders } from "./utils";
import type { VideoPreview } from "../src/lib/api/types";

vi.mock("@api/videoApi", () => ({
    default: {},
    getVideos: vi.fn(),
    getVideoPreviewsByCategory: vi.fn(),
    getVideo: vi.fn(),
}));

vi.mock("@api/categoriesApi", () => ({
    default: { getCategories: vi.fn() },
}));

// Keep the grid simple: one testable node per card.
vi.mock("@/components/VideoCard", () => ({
    default: ({ title, loading }: { title?: string; loading?: boolean }) => (
        <div data-testid="video-card">{loading ? "Loading..." : title}</div>
    ),
}));

vi.mock("@/components/infinite-scroll", () => ({
    default: ({ children }: { children: React.ReactNode }) => (
        <div data-testid="infinite-scroll">{children}</div>
    ),
}));

import { getVideos } from "@api/videoApi";
import categoriesApi from "@api/categoriesApi";

const mockedGetVideos = vi.mocked(getVideos);
const mockedGetCategories = vi.mocked(categoriesApi.getCategories);

function makeVideo(i: number): VideoPreview {
    return {
        id: `video-${i}`,
        title: `Mock Video ${i}`,
        name: `Mock Video ${i}`,
        previewUrl: `/thumb-${i}.jpg`,
        thumbnail_url: `/thumb-${i}.jpg`,
        channel_avatar: "",
        channel_name: "Channel",
        channel: "Channel",
        createdAt: "2025-01-01T00:00:00Z",
        publishedAt: "2025-01-01T00:00:00Z",
        views: i * 10,
        likesCount: 0,
        dislikesCount: 0,
        privacy: "public",
        status: "Ready",
    };
}

describe("Home", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockedGetCategories.mockResolvedValue([{ id: "gaming", name: "gaming" }]);
    });

    it("shows loading skeletons, then the fetched videos", async () => {
        mockedGetVideos.mockResolvedValue([makeVideo(1), makeVideo(2), makeVideo(3)]);

        renderWithProviders(<Home />);

        // First paint: skeleton cards while the query is in flight.
        expect(screen.getAllByTestId("video-card")[0]).toHaveTextContent("Loading...");

        await waitFor(() => {
            expect(screen.getByText("Mock Video 1")).toBeInTheDocument();
        });

        expect(screen.getAllByTestId("video-card")).toHaveLength(3);
        expect(screen.getByTestId("infinite-scroll")).toBeInTheDocument();
        expect(screen.getByText("Mock Video 1").closest("a")).toHaveAttribute(
            "href",
            "/watch?v=video-1",
        );
    });

    it("renders the category pills with 'All' prepended", async () => {
        mockedGetVideos.mockResolvedValue([]);

        renderWithProviders(<Home />);

        await waitFor(() => {
            expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: /gaming/i })).toBeInTheDocument();
        });
    });

    it("shows an error state instead of skeletons when the request fails", async () => {
        mockedGetVideos.mockRejectedValue(new Error("Network Error"));

        renderWithProviders(<Home />);

        await waitFor(() => {
            expect(screen.getByText("Couldn't load videos")).toBeInTheDocument();
        });
        expect(screen.queryByText("Loading...")).not.toBeInTheDocument();
    });
});
