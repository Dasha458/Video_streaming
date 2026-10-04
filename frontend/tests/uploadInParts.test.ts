import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/clientApi", () => ({
    default: { post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import clientApi from "@/lib/api/clientApi";
import {
    findResumableUpload,
    forgetUpload,
    rememberUpload,
    uploadInParts,
} from "@/lib/api/uploadApi";

const PART = 10;

function file(size: number, name = "clip.mp4", lastModified = 1000): File {
    const f = new File([new Uint8Array(size)], name, { type: "video/mp4" });
    Object.defineProperty(f, "lastModified", { value: lastModified });
    return f;
}

const meta = {
    title: "clip",
    description: "",
    privacy: "public" as const,
    category: "music",
};

function started(partSize = PART) {
    return { data: { upload_id: "u1", part_size: partSize, total_parts: 3 } };
}

function status(received: number[], partSize = PART) {
    return {
        data: {
            upload_id: "u1",
            part_size: partSize,
            declared_size: 25,
            received_parts: received,
            received_bytes: received.length * partSize,
        },
    };
}

describe("uploadInParts", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
        vi.mocked(clientApi.put).mockResolvedValue(status([]) as never);
        vi.mocked(clientApi.post).mockResolvedValue({ data: {} } as never);
    });

    it("sends the file as parts rather than one request", async () => {
        // The whole point: a 500 MB body fails entirely on any dropped
        // connection, and forces the gateway to accept a body that size.
        vi.mocked(clientApi.post).mockResolvedValueOnce(started() as never);

        await uploadInParts(file(25), meta);

        expect(vi.mocked(clientApi.put)).toHaveBeenCalledTimes(3);
        const parts = vi
            .mocked(clientApi.put)
            .mock.calls.map((call) => call[0] as string);
        expect(parts).toEqual([
            "/api/files/uploads/u1/parts/1",
            "/api/files/uploads/u1/parts/2",
            "/api/files/uploads/u1/parts/3",
        ]);
    });

    it("skips the parts the server already holds", async () => {
        // This is what makes an interrupted upload cheap: after a crash
        // the client asks what arrived instead of starting again.
        const f = file(25);
        rememberUpload("u1", f);
        vi.mocked(clientApi.get).mockResolvedValue(status([1, 2]) as never);

        await uploadInParts(f, meta);

        expect(vi.mocked(clientApi.post)).not.toHaveBeenCalledWith(
            "/api/files/uploads",
            expect.anything(),
        );
        expect(vi.mocked(clientApi.put)).toHaveBeenCalledTimes(1);
        expect(vi.mocked(clientApi.put).mock.calls[0][0]).toBe(
            "/api/files/uploads/u1/parts/3",
        );
    });

    it("reports progress by bytes, including what was already there", async () => {
        const f = file(25);
        rememberUpload("u1", f);
        vi.mocked(clientApi.get).mockResolvedValue(status([1, 2]) as never);
        const seen: number[] = [];

        await uploadInParts(f, meta, (p) => seen.push(p.ratio));

        // Starts at 20/25, not at zero: the bar must not pretend the
        // finished parts are gone.
        expect(seen[0]).toBeCloseTo(0.8, 5);
        expect(seen.at(-1)).toBeCloseTo(1, 5);
    });

    it("starts over when the remembered upload is gone", async () => {
        // Swept as abandoned, or belonging to another account now.
        const f = file(25);
        rememberUpload("u1", f);
        vi.mocked(clientApi.get).mockRejectedValue(new Error("404") as never);
        vi.mocked(clientApi.post).mockResolvedValueOnce(started() as never);

        await uploadInParts(f, meta);

        expect(vi.mocked(clientApi.post).mock.calls[0][0]).toBe("/api/files/uploads");
    });

    it("retries a failed part instead of losing the upload", async () => {
        // A part failing is the ordinary case this design exists for.
        vi.mocked(clientApi.post).mockResolvedValueOnce(started(25) as never);
        vi.mocked(clientApi.put)
            .mockRejectedValueOnce(new Error("connection reset") as never)
            .mockResolvedValue(status([]) as never);

        await uploadInParts(file(25), meta);

        expect(vi.mocked(clientApi.put)).toHaveBeenCalledTimes(2);
    });

    it("forgets the upload once it is finished", async () => {
        const f = file(25);
        vi.mocked(clientApi.post).mockResolvedValueOnce(started() as never);

        await uploadInParts(f, meta);

        expect(findResumableUpload(f)).toBeNull();
    });
});

describe("findResumableUpload", () => {
    beforeEach(() => localStorage.clear());

    it("recognises the same file", () => {
        const f = file(25);
        rememberUpload("u1", f);

        expect(findResumableUpload(f)).toBe("u1");
    });

    it("refuses a different file of the same name", () => {
        // Resuming into a different file would assemble parts of two
        // videos into one object.
        rememberUpload("u1", file(25, "clip.mp4", 1000));

        expect(findResumableUpload(file(30, "clip.mp4", 1000))).toBeNull();
        expect(findResumableUpload(file(25, "clip.mp4", 2000))).toBeNull();
        expect(findResumableUpload(file(25, "other.mp4", 1000))).toBeNull();
    });

    it("survives storage being unavailable", () => {
        // Private browsing throws on every access; an upload must not.
        const broken = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("denied");
        });

        expect(() => findResumableUpload(file(25))).not.toThrow();
        expect(findResumableUpload(file(25))).toBeNull();

        broken.mockRestore();
        forgetUpload();
    });
});
