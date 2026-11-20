import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ApiClient, type DocumentInfo } from "../api";
import { formatBytes, validateFile } from "../api/validation";
import { DocIcon, UploadIcon } from "./icons";
import { POLL_START_MS, isUnresolved, nextPollDelay, statusLabel } from "./status";
import { MAX_PARALLEL, failureReason, planUploads, type QueueItem } from "./uploadQueue";

interface Props {
  api: ApiClient;
  onChange?: (docs: DocumentInfo[]) => void;
}

export function DocumentList({ api, onChange }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pollDelay = useRef(POLL_START_MS);
  const seq = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const list = await api.listDocuments();
      setDocs(list);
      onChange?.(list);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load documents.");
    }
  }, [api, onChange]);

  // First load: ignore the result if the component unmounted meanwhile.
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

  // Poll while something is still changing: 2 s, 3 s, 4.5 s ... capped at 10 s.
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

  const patch = (id: number, change: Partial<QueueItem>) =>
    setQueue((q) => q.map((item) => (item.id === id ? { ...item, ...change } : item)));

  async function uploadOne(item: QueueItem, file: File) {
    patch(item.id, { state: "uploading" });
    try {
      await api.uploadDocument(file, (f) => patch(item.id, { progress: f }));
      patch(item.id, { state: "done", progress: 1 });
      pollDelay.current = POLL_START_MS; // a new document: check quickly again
      await refresh();
      setTimeout(() => setQueue((q) => q.filter((i) => i.id !== item.id)), 1200);
    } catch (e) {
      patch(item.id, { state: "error", error: e instanceof ApiError ? e.message : "Upload failed." });
    }
  }

  async function addFiles(files: File[]) {
    setError(null);
    const { accepted, rejected } = planUploads(files, docs.length, validateFile);
    const make = (name: string, extra: Partial<QueueItem>): QueueItem => ({
      id: ++seq.current, name, progress: 0, state: "waiting", ...extra,
    });
    const rejectedItems = rejected.map((r) => make(r.file.name, { state: "error", error: r.reason }));
    const work = accepted.map((file) => ({ file, item: make(file.name, {}) }));
    setQueue((q) => [...q, ...work.map((w) => w.item), ...rejectedItems]);
    if (input.current) input.current.value = "";

    // At most MAX_PARALLEL uploads at a time, so a big batch doesn't hit the API's rate limit.
    let next = 0;
    const runner = async () => {
      while (next < work.length) {
        const w = work[next++]!;
        await uploadOne(w.item, w.file);
      }
    };
    await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, work.length) }, runner));
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

  const ready = docs.filter((d) => d.status === "READY").length;

  return (
    <section className="docs" aria-labelledby="docs-h">
      <div className="docs__head">
        <h2 id="docs-h" className="docs__title">
          Documents
        </h2>
        <span className="docs__count" aria-label={`${docs.length} of 5 documents, ${ready} ready`}>
          {docs.length} of 5
        </span>
      </div>

      <div className="docs__panel">
        <label
          className={`drop${dragOver ? " drop--over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            void addFiles(Array.from(e.dataTransfer.files));
          }}
        >
          <UploadIcon className="drop__icon" />
          <span className="drop__title">
            Drop PDFs here or <span className="drop__browse">browse</span>
          </span>
          <span className="drop__hint">Several at once · text PDFs · 10 MB max</span>
          <input
            ref={input}
            className="drop__input"
            type="file"
            accept="application/pdf"
            multiple
            aria-label="Choose PDF files to upload"
            onChange={(e) => void addFiles(Array.from(e.target.files ?? []))}
          />
        </label>

        {queue.length > 0 && (
          <ul className="queue" aria-label="Uploads">
            {queue.map((q) => (
              <li key={q.id} className="queue__item">
                <div className="queue__row">
                  <span className="queue__name">{q.name}</span>
                  <span className="queue__pct">
                    {q.state === "error" ? "Not uploaded" : q.state === "done" ? "Done" : `${Math.round(q.progress * 100)}%`}
                  </span>
                </div>
                {q.state === "error" ? (
                  <p className="queue__error" role="alert">
                    {q.error}
                  </p>
                ) : (
                  <div
                    className="bar"
                    role="progressbar"
                    aria-label={`Uploading ${q.name}`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(q.progress * 100)}
                  >
                    <div className="bar__fill" style={{ width: `${Math.round(q.progress * 100)}%` }} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        {docs.length === 0 ? (
          <p className="empty">No documents yet. Upload a PDF to start asking questions about it.</p>
        ) : (
          <ul className="doc-list">
            {docs.map((d) => {
              const reason = d.status === "FAILED" ? failureReason(d.errorCode) : null;
              return (
                <li key={d.documentId} className="doc">
                  <DocIcon className="doc__icon" size={18} />
                  <div className="doc__body">
                    <div className="doc__name" title={d.filename}>
                      {d.filename}
                    </div>
                    <div className={`doc__meta${reason ? " doc__meta--warn" : ""}`}>{reason ?? formatBytes(d.fileSize)}</div>
                  </div>
                  <StatusPill status={d.status} />
                  {api.canDelete && (
                    <button
                      type="button"
                      className="btn btn-ghost icon-btn"
                      aria-label={`Delete ${d.filename}`}
                      disabled={d.status === "DELETING"}
                      onClick={() => void remove(d.documentId)}
                    >
                      ×
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function StatusPill({ status }: { status: DocumentInfo["status"] }) {
  const cls = status === "READY" ? "pill pill--ready" : status === "FAILED" ? "pill pill--failed" : "pill";
  return (
    <span className={cls}>
      {isUnresolved(status) && <span className="pill__dot" aria-hidden="true" />}
      {statusLabel(status)}
    </span>
  );
}
