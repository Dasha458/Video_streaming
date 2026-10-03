import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "./utils";

vi.mock("@api/videoApi", () => ({
    default: {
        getVideos: vi.fn(),
        deleteVideo: vi.fn(),
        updateVideoPrivacy: vi.fn(),
    },
}));

const toastSpy = vi.fn();
vi.mock("@/components/ui/toast/use-toast", () => ({
    toast: (...args: unknown[]) => toastSpy(...args),
    useToast: () => ({ toast: toastSpy, toasts: [], dismiss: vi.fn() }),
}));

import videoApi from "@api/videoApi";
import YourVideos from "../src/pages/YourVideos";

const video = (overrides: Record<string, unknown> = {}) => ({
    id: "v1",
    title: "A clip",
    thumbnail: "",
    channel_avatar: "",
    channel_name: "someone",
    views_count: 0,
    likes_count: 0,
    dislikes_count: 0,
    privacy: "public",
    status: "Ready",
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
});

async function openMenu() {
    const trigger = await screen.findByRole("button", { name: "" });
    await userEvent.click(trigger);
}

describe("YourVideos — the video menu", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(videoApi.getVideos).mockResolvedValue([video()] as never);
    });

    it("asks before deleting, in the app's own dialog", async () => {
        // This used to be window.confirm -- the only native dialog left in
        // the frontend, in an app that has its own.
        const nativeConfirm = vi.fn(() => true);
        vi.stubGlobal("confirm", nativeConfirm);

        renderWithProviders(<YourVideos />);
        await openMenu();
        await userEvent.click(await screen.findByText("Delete"));

        expect(await screen.findByText("Delete this video?")).toBeInTheDocument();
        expect(nativeConfirm).not.toHaveBeenCalled();
        // Nothing is deleted until the dialog is answered.
        expect(videoApi.deleteVideo).not.toHaveBeenCalled();
    });

    it("deletes once the dialog is confirmed", async () => {
        vi.mocked(videoApi.deleteVideo).mockResolvedValue(undefined as never);

        renderWithProviders(<YourVideos />);
        await openMenu();
        await userEvent.click(await screen.findByText("Delete"));
        const dialog = await screen.findByRole("dialog");
        await userEvent.click(
            await screen.findByRole("button", { name: "Delete" }),
        );

        await waitFor(() => expect(videoApi.deleteVideo).toHaveBeenCalledWith("v1"));
        expect(dialog).toBeTruthy();
    });

    it("says what the server said when a delete fails", async () => {
        // It used to show a fixed "Failed to delete video" and drop the
        // explanation on the floor.
        // A real AxiosError: getApiErrorMessage only unwraps those, which is
        // what axios actually throws.
        const failure = new AxiosError("Request failed");
        failure.response = {
            data: { code: "VIDEO_NOT_FOUND", message: "Still being encoded" },
            status: 404,
            statusText: "Not Found",
            headers: {},
            config: {} as never,
        };
        vi.mocked(videoApi.deleteVideo).mockRejectedValue(failure as never);

        renderWithProviders(<YourVideos />);
        await openMenu();
        await userEvent.click(await screen.findByText("Delete"));
        await userEvent.click(
            await screen.findByRole("button", { name: "Delete" }),
        );

        await waitFor(() =>
            expect(toastSpy).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Still being encoded" }),
            ),
        );
    });

    it.each(["Processing", "Queued"])(
        "does not offer delete while the encoder is still writing (%s)",
        async (status) => {
            // The server refuses it for these, so the action could only fail.
            vi.mocked(videoApi.getVideos).mockResolvedValue([
                video({ status }),
            ] as never);

            renderWithProviders(<YourVideos />);
            await openMenu();

            expect(await screen.findByText("Watch")).toBeInTheDocument();
            expect(screen.queryByText("Delete")).not.toBeInTheDocument();
        },
    );

    it("offers delete for a failed encode", async () => {
        // The state people most want to clear, and the one that used to be
        // impossible to delete at all.
        vi.mocked(videoApi.getVideos).mockResolvedValue([
            video({ status: "Failed" }),
        ] as never);

        renderWithProviders(<YourVideos />);
        await openMenu();

        expect(await screen.findByText("Delete")).toBeInTheDocument();
    });
});
