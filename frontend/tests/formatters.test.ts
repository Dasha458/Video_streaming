import { describe, it, expect } from "vitest";
import {
    formatCompact,
    formatViews,
    formatSubscribers,
    formatSeconds,
    formatCategoryName,
} from "@/utils/formatters";

/**
 * There used to be five of these, disagreeing with each other: the same
 * 1000 rendered as "1K views", "1K", "1.0K" and "1k" depending on the
 * screen. These tests pin the one answer down.
 */
describe("formatCompact", () => {
    it("leaves small numbers alone", () => {
        expect(formatCompact(0)).toBe("0");
        expect(formatCompact(999)).toBe("999");
    });

    it("drops a trailing .0 instead of printing 1.0K", () => {
        expect(formatCompact(1_000)).toBe("1K");
        expect(formatCompact(2_000_000)).toBe("2M");
    });

    it("keeps one decimal when it carries information", () => {
        expect(formatCompact(1_500)).toBe("1.5K");
        expect(formatCompact(2_400_000)).toBe("2.4M");
    });

    it("treats a missing count as zero", () => {
        expect(formatCompact(undefined)).toBe("0");
    });
});

describe("formatViews", () => {
    it("is empty for an unknown count so callers can filter it out", () => {
        expect(formatViews(undefined)).toBe("");
    });

    it("agrees with the number in the singular", () => {
        expect(formatViews(1)).toBe("1 view");
        expect(formatViews(2)).toBe("2 views");
        expect(formatViews(1_500)).toBe("1.5K views");
    });
});

describe("formatSubscribers", () => {
    it("reads naturally at every scale", () => {
        expect(formatSubscribers(undefined)).toBe("0 subscribers");
        expect(formatSubscribers(1)).toBe("1 subscriber");
        expect(formatSubscribers(1_200_000)).toBe("1.2M subscribers");
    });
});

describe("formatSeconds", () => {
    it("drops the units that would read as zero", () => {
        expect(formatSeconds(0)).toBe("0s");
        expect(formatSeconds(45)).toBe("45s");
        expect(formatSeconds(125)).toBe("2m 5s");
        expect(formatSeconds(3_900)).toBe("1h 5m");
    });
});

describe("formatCategoryName", () => {
    it("title-cases each word", () => {
        expect(formatCategoryName("science and tech")).toBe("Science And Tech");
    });
});
