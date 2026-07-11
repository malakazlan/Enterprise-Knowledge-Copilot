"use client";

/** Library: upload, list, and delete documents. */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";
import type { DocumentRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, EmptyState, Pill, Spinner, TableSkeleton } from "@/components/ui";

function formatSize(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function extractionPill(doc: DocumentRead) {
  const ocrPages = doc.doc_metadata["ocr_pages"];
  if (typeof ocrPages === "number" && ocrPages > 0) return <Pill tone="ok">OCR</Pill>;
  if (doc.content_type.startsWith("image/")) return <Pill tone="ok">OCR</Pill>;
  return <Pill tone="gray">Text layer</Pill>;
}

function statusPill(status: DocumentRead["status"]) {
  switch (status) {
    case "completed":
      return <Pill tone="ok" dot>Ingested</Pill>;
    case "failed":
      return <Pill tone="danger" dot>Failed</Pill>;
    default:
      return <Pill tone="warn" dot>Processing</Pill>;
  }
}

export default function LibraryPage() {
  const [docs, setDocs] = useState<DocumentRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    listDocuments()
      .then(setDocs)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server."),
      );
  }, []);

  useEffect(refresh, [refresh]);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(file);
      }
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(doc: DocumentRead) {
    if (!window.confirm(`Delete “${doc.filename}” and all its chunks?`)) return;
    try {
      await deleteDocument(doc.id);
      setDocs((prev) => prev?.filter((d) => d.id !== doc.id) ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    }
  }

  return (
    <div>
      <PageHead
        title="Library"
        desc="Everything the copilot can answer from. Scanned PDFs and images are OCR’d automatically."
      />

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        className={`mb-5 flex cursor-pointer items-center gap-4 rounded-xl border-[1.5px] border-dashed p-6 transition-colors ${
          dragging ? "border-accent bg-accent-subtle" : "border-line-strong hover:border-accent hover:bg-accent-subtle"
        }`}
      >
        <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[10px] bg-accent-subtle text-lg text-accent">
          ↑
        </span>
        <span>
          <span className="block text-sm font-semibold">Drop files to upload, or browse</span>
          <span className="mt-0.5 block text-[12.5px] text-ink-2">
            pdf · png / jpg · md · txt — processed on this server, nothing leaves it
          </span>
        </span>
        <span className="ml-auto">
          {busy ? <Spinner /> : <Button variant="primary">Upload</Button>}
        </span>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.md,.txt"
          className="hidden"
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {error && (
        <div className="mb-4">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}

      <Card className="overflow-hidden">
        {docs === null ? (
          <TableSkeleton rows={5} />
        ) : docs.length === 0 ? (
          <EmptyState
            title="No documents yet"
            hint="Upload your first document above — it becomes searchable in seconds."
          />
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="bg-subtle text-left text-xs font-semibold text-ink-2">
                <th className="px-4 py-2.5">Document</th>
                <th className="px-4 py-2.5">Extraction</th>
                <th className="px-4 py-2.5">Pages</th>
                <th className="px-4 py-2.5">Size</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Added</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id} className="group border-t border-line transition-colors hover:bg-subtle">
                  <td className="px-4 py-3 font-semibold">{doc.filename}</td>
                  <td className="px-4 py-3">{extractionPill(doc)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {doc.page_count ?? "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {formatSize(doc.size_bytes)}
                  </td>
                  <td className="px-4 py-3">{statusPill(doc.status)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {formatDate(doc.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="flex justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <Link
                        href={`/viewer/?doc=${doc.id}`}
                        className="rounded-lg px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-hover hover:text-ink"
                      >
                        Open
                      </Link>
                      <Button variant="ghost" small className="text-danger" onClick={() => void remove(doc)}>
                        Delete
                      </Button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
