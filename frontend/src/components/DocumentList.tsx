import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ApiClient, type DocumentInfo } from "../api";
import { formatBytes, validateFile } from "../api/validation";

const POLL_MS = 2000;

interface Props {
  api: ApiClient;
  onChange?: (docs: DocumentInfo[]) => void;
}

export function DocumentList({ api, onChange }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.listDocuments();
      setDocs(list);
      onChange?.(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load documents.");
    }
  }, [api, onChange]);

  useEffect(() => {
    let cancelled = false;
    api
      .listDocuments()
      .then((list) => {
        if (cancelled) return;
        setDocs(list);
        onChange?.(list);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load documents.");
      });
    return () => {
      cancelled = true;
    };
  }, [api, onChange]);

  const unresolved = docs.some((d) => ["PENDING_UPLOAD", "UPLOADED", "INDEXING", "DELETING"].includes(d.status));
  useEffect(() => {
    if (!unresolved) return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [unresolved, refresh]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    const problem = validateFile(file);
    if (problem) return setError(problem);
    setBusy(true);
    try {
      await api.uploadDocument(file);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteDocument(id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed.");
    }
  }

  return (
    <section aria-labelledby="docs-h">
      <h2 id="docs-h">Documents</h2>
      <label>
        Upload a PDF (max 10 MB){" "}
        <input
          ref={input}
          type="file"
          accept="application/pdf"
          disabled={busy}
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </label>
      {busy && <p role="status">Uploading…</p>}
      {error && <p role="alert">{error}</p>}
      {docs.length === 0 ? (
        <p>No documents yet.</p>
      ) : (
        <ul>
          {docs.map((d) => (
            <li key={d.documentId}>
              <strong>{d.filename}</strong> ({formatBytes(d.fileSize)}) — <span data-status={d.status}>{d.status}</span>
              {d.errorCode && <em> ({d.errorCode})</em>}{" "}
              <button onClick={() => void remove(d.documentId)} disabled={d.status === "DELETING"}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
