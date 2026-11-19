import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ApiClient, type DocumentInfo } from "../api";
import { formatBytes, validateFile } from "../api/validation";
import { POLL_START_MS, isUnresolved, nextPollDelay, statusLabel } from "./status";

interface Props {
  api: ApiClient;
  onChange?: (docs: DocumentInfo[]) => void;
}

export function DocumentList({ api, onChange }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pollDelay = useRef(POLL_START_MS);

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

  // Poll while something is still changing: 2 s, then 3 s, 4.5 s ... capped at 10 s.
  // Each refresh replaces `docs`, which re-runs this effect and schedules the next poll.
  const unresolved = docs.some((d) => isUnresolved(d.status));
  useEffect(() => {
    if (!unresolved) {
      pollDelay.current = POLL_START_MS;
      return;
    }
    const t = setTimeout(() => {
      pollDelay.current = nextPollDelay(pollDelay.current);
      void refresh();
    }, pollDelay.current);
    return () => clearTimeout(t);
  }, [unresolved, refresh, docs]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    const problem = validateFile(file);
    if (problem) return setError(problem);
    setBusy(true);
    try {
      await api.uploadDocument(file);
      pollDelay.current = POLL_START_MS; // a new document: check quickly again
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
              <strong>{d.filename}</strong> ({formatBytes(d.fileSize)}) — <span data-status={d.status}>{statusLabel(d.status)}</span>
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
