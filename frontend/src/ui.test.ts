import { describe, expect, it } from "vitest";
import { validateFile } from "./api/validation";
import { failureReason, planUploads } from "./components/uploadQueue";
import { isVietnamese, stringsFor } from "./lang";
import { brandAssets, initialTheme } from "./theme";

const pdf = (name: string, size = 100) => new File([new Uint8Array(size)], name, { type: "application/pdf" });

describe("upload queue (UI-03)", () => {
  it("accepts several PDFs and rejects bad files individually", () => {
    const txt = new File(["x"], "notes.txt", { type: "text/plain" });
    const plan = planUploads([pdf("a.pdf"), txt, pdf("b.pdf")], 0, validateFile);
    expect(plan.accepted.map((f) => f.name)).toEqual(["a.pdf", "b.pdf"]);
    expect(plan.rejected.map((r) => r.file.name)).toEqual(["notes.txt"]);
  });
  it("stops at the 5-document limit with a reason", () => {
    const plan = planUploads([pdf("a.pdf"), pdf("b.pdf"), pdf("c.pdf")], 3, validateFile);
    expect(plan.accepted).toHaveLength(2);
    expect(plan.rejected[0]!.reason).toMatch(/limit is 5/);
  });
  it("explains failure codes in plain language", () => {
    expect(failureReason("INDEXING_FAILED")).toMatch(/No readable text/);
    expect(failureReason(null)).toMatch(/Upload it again/);
  });
});

describe("language (UI-06)", () => {
  it("detects Vietnamese by its own letters, not shared accents", () => {
    expect(isVietnamese("Ngân sách năm 2026 của dự án Sen Vàng là bao nhiêu?")).toBe(true);
    expect(isVietnamese("Ai là kỹ sư trưởng?")).toBe(true);
    expect(isVietnamese("What is the café budget?")).toBe(false);
    expect(isVietnamese("Où est la réunion?")).toBe(false);
  });
  it("picks the decline note in the question's language", () => {
    expect(stringsFor("Thời tiết hôm nay thế nào?").noSourceNote).toMatch(/^Không có nguồn/);
    expect(stringsFor("What's the weather?").noSourceNote).toMatch(/^No source/);
  });
});

describe("theme (UI-02)", () => {
  it("uses a saved choice, then the system setting, defaulting to dark", () => {
    expect(initialTheme("light", false)).toBe("light");
    expect(initialTheme(null, true)).toBe("light");
    expect(initialTheme(null, false)).toBe("dark");
    expect(initialTheme("bogus", false)).toBe("dark");
  });
  it("serves the logo and mark that suit each theme", () => {
    expect(brandAssets("dark")).toEqual({ logo: "/brand/logo-on-dark.svg", mark: "/brand/mark-on-dark.svg" });
    expect(brandAssets("light").logo).toBe("/brand/logo-on-light.svg");
  });
});
