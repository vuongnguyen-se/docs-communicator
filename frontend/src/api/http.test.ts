import { describe, expect, it } from "vitest";
import { parseConfig } from "../config";
import { HttpApi, toApiError } from "./http";

interface Call {
  url: string;
  init: RequestInit;
}

function fakeFetch(responses: Array<{ status: number; body?: unknown }>) {
  const calls: Call[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    const r = responses.shift() ?? { status: 500 };
    const text = r.body === undefined ? "" : JSON.stringify(r.body);
    return new Response(r.status === 204 ? null : text, { status: r.status });
  };
  return { fn: fn as typeof fetch, calls };
}

const token = async () => "tok-123";
const doc = {
  documentId: "doc_" + "a".repeat(32),
  filename: "a.pdf",
  fileSize: 10,
  status: "PENDING_UPLOAD",
  createdAt: "t",
  updatedAt: "t",
  errorCode: null,
};

describe("HttpApi", () => {
  it("sends the bearer token and parses /me", async () => {
    const f = fakeFetch([{ status: 200, body: { userId: "sub-1" } }]);
    const api = new HttpApi("https://api.example.com/", token, f.fn);
    expect(await api.whoAmI()).toBe("sub-1");
    expect(f.calls[0]!.url).toBe("https://api.example.com/me");
    expect((f.calls[0]!.init.headers as Record<string, string>).authorization).toBe("Bearer tok-123");
  });

  it("maps the backend error shape to ApiError", async () => {
    const f = fakeFetch([{ status: 409, body: { error: { code: "LIMIT_EXCEEDED", message: "limit" } } }]);
    const api = new HttpApi("https://api.example.com", token, f.fn);
    await expect(api.listDocuments()).rejects.toMatchObject({ code: "LIMIT_EXCEEDED", status: 409 });
  });

  it("uploads via presigned POST without leaking the token to S3, then completes", async () => {
    const f = fakeFetch([
      { status: 201, body: { document: doc, upload: { url: "https://bucket.s3.amazonaws.com/", fields: { key: "k", policy: "p" } }, expiresInSeconds: 300 } },
      { status: 204 },
      { status: 202, body: { document: { ...doc, status: "INDEXING" } } },
    ]);
    const api = new HttpApi("https://api.example.com", token, f.fn);
    const file = new File([new Uint8Array(10)], "a.pdf", { type: "application/pdf" });

    const result = await api.uploadDocument(file);

    expect(result.status).toBe("INDEXING");
    const [, s3, complete] = f.calls;
    expect(s3!.url).toBe("https://bucket.s3.amazonaws.com/");
    expect(s3!.init.headers).toBeUndefined();
    const form = s3!.init.body as FormData;
    expect([...form.keys()]).toEqual(["key", "policy", "file"]);
    expect(complete!.url).toBe(`https://api.example.com/documents/${doc.documentId}/complete`);
  });

  it("rejects invalid files before calling the API", async () => {
    const f = fakeFetch([]);
    const api = new HttpApi("https://api.example.com", token, f.fn);
    const txt = new File(["x"], "a.txt", { type: "text/plain" });
    await expect(api.uploadDocument(txt)).rejects.toMatchObject({ code: "VALIDATION_ERROR" });
    expect(f.calls).toHaveLength(0);
  });

  it("gives friendly messages for gateway errors without a body", () => {
    expect(toApiError(401, null).code).toBe("UNAUTHORIZED");
    expect(toApiError(429, { message: "Too Many Requests" }).code).toBe("THROTTLED");
  });
});

describe("parseConfig", () => {
  it("defaults to mock", () => {
    expect(parseConfig({}).mode).toBe("mock");
  });
  it("requires every field in http mode and https", () => {
    expect(() => parseConfig({ mode: "http", apiUrl: "https://x" })).toThrow(/missing/);
    expect(() =>
      parseConfig({ mode: "http", apiUrl: "http://x", region: "r", userPoolId: "p", userPoolClientId: "c" }),
    ).toThrow(/https/);
    expect(
      parseConfig({ mode: "http", apiUrl: "https://x/", region: "r", userPoolId: "p", userPoolClientId: "c" }).apiUrl,
    ).toBe("https://x");
  });
});
