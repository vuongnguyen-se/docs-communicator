import { describe, expect, it } from "vitest";
import { MockApi } from "./mock";
import { validateFile, validateQuestion } from "./validation";

const pdf = (name = "a.pdf", size = 100) => new File([new Uint8Array(size)], name, { type: "application/pdf" });

describe("validation", () => {
  it("rejects non-pdf and oversize files", () => {
    expect(validateFile({ name: "a.txt", size: 1, type: "text/plain" })).not.toBeNull();
    expect(validateFile({ name: "a.pdf", size: 11 * 1024 * 1024, type: "application/pdf" })).not.toBeNull();
    expect(validateFile({ name: "a.pdf", size: 10, type: "application/pdf" })).toBeNull();
  });
  it("rejects empty and long questions", () => {
    expect(validateQuestion("  ")).not.toBeNull();
    expect(validateQuestion("x".repeat(2001))).not.toBeNull();
    expect(validateQuestion("hi")).toBeNull();
  });
});

describe("MockApi", () => {
  it("moves a document from INDEXING to READY", async () => {
    const api = new MockApi(30, 0);
    const doc = await api.uploadDocument(pdf());
    expect(doc.status).toBe("INDEXING");
    await new Promise((r) => setTimeout(r, 50));
    expect((await api.getDocument(doc.documentId)).status).toBe("READY");
  });

  it("returns uncertainty with no citations when nothing is READY", async () => {
    const api = new MockApi(10_000, 0);
    await api.uploadDocument(pdf());
    const res = await api.ask("anything");
    expect(res.citations).toEqual([]);
  });

  it("cites a READY document", async () => {
    const api = new MockApi(0, 0);
    await api.uploadDocument(pdf("tài-liệu.pdf"));
    const res = await api.ask("Tài liệu này nói về gì?");
    expect(res.citations[0]?.documentName).toBe("tài-liệu.pdf");
    const declined = await api.ask("What is the weather today?");
    expect(declined.citations).toEqual([]);
  });

  it("enforces the document limit and deletes", async () => {
    const api = new MockApi(0, 0);
    for (let i = 0; i < 5; i++) await api.uploadDocument(pdf(`${i}.pdf`));
    await expect(api.uploadDocument(pdf("x.pdf"))).rejects.toMatchObject({ code: "LIMIT_EXCEEDED" });
    const [first] = await api.listDocuments();
    await api.deleteDocument(first!.documentId);
    expect(await api.listDocuments()).toHaveLength(4);
  });
});
