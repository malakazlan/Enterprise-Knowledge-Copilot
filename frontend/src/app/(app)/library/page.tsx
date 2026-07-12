"use client";

/** Library: upload, browse, and delete documents; manage collections. */

import Link from "next/link";
import { FolderLock, Trash2, Upload, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import {
  addCollectionMember,
  ApiError,
  createCollection,
  deleteCollection,
  deleteDocument,
  listCollectionMembers,
  listCollections,
  listDocuments,
  me,
  removeCollectionMember,
  uploadDocument,
} from "@/lib/api";
import type { CollectionMemberRead, CollectionRead, DocumentRead } from "@/lib/types";
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
  return <Pill tone="gray">Text</Pill>;
}

function isStale(doc: DocumentRead): boolean {
  return doc.verify_by !== null && new Date(doc.verify_by).getTime() < Date.now();
}

function statusPill(status: DocumentRead["status"]) {
  switch (status) {
    case "completed":
      return (
        <Pill tone="ok" dot>
          Ingested
        </Pill>
      );
    case "failed":
      return (
        <Pill tone="danger" dot>
          Failed
        </Pill>
      );
    default:
      return (
        <Pill tone="warn" dot>
          Processing
        </Pill>
      );
  }
}

function CollectionRow({
  collection,
  onChanged,
}: {
  collection: CollectionRead;
  onChanged: () => void;
}) {
  const [members, setMembers] = useState<CollectionMemberRead[] | null>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadMembers = useCallback(() => {
    listCollectionMembers(collection.id)
      .then(setMembers)
      .catch(() => setMembers([]));
  }, [collection.id]);

  useEffect(loadMembers, [loadMembers]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await addCollectionMember(collection.id, email.trim());
      setEmail("");
      loadMembers();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add member.");
    }
  }

  async function removeMember(userId: string) {
    await removeCollectionMember(collection.id, userId).catch(() => undefined);
    loadMembers();
    onChanged();
  }

  async function remove() {
    if (
      !window.confirm(
        `Delete collection “${collection.name}”? Its documents become shared with everyone.`,
      )
    )
      return;
    await deleteCollection(collection.id).catch(() => undefined);
    onChanged();
  }

  return (
    <div className="border-t border-line px-4 py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2.5">
        <FolderLock size={14} className="text-ink-3" />
        <span className="text-[13.5px] font-semibold">{collection.name}</span>
        <Pill tone="gray">{collection.document_count} docs</Pill>
        <span className="ml-auto">
          <Button variant="ghost" small className="text-danger" onClick={() => void remove()}>
            <Trash2 size={13} /> Delete
          </Button>
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {members === null ? (
          <Spinner />
        ) : (
          members.map((m) => (
            <span
              key={m.user_id}
              className="inline-flex items-center gap-1 rounded-full bg-subtle px-2.5 py-0.5 text-xs text-ink-2"
            >
              {m.email}
              <button
                onClick={() => void removeMember(m.user_id)}
                className="text-ink-3 hover:text-danger"
                title="Remove access"
              >
                <X size={11} />
              </button>
            </span>
          ))
        )}
        <form onSubmit={add} className="flex items-center gap-1.5">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="add member by email…"
            type="email"
            className="w-[200px] rounded-full border border-line bg-canvas px-3 py-0.5 text-xs placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={!email.trim()}
            className="grid h-6 w-6 place-items-center rounded-full text-ink-3 hover:bg-subtle hover:text-accent disabled:opacity-40"
            title="Grant access"
          >
            <UserPlus size={13} />
          </button>
        </form>
      </div>
      {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
    </div>
  );
}

function CollectionsPanel({
  collections,
  onChanged,
}: {
  collections: CollectionRead[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createCollection(name.trim(), null);
      setName("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create collection.");
    }
  }

  return (
    <Card className="mb-5 overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <h2 className="text-[14px] font-semibold">Collections</h2>
        <p className="text-xs text-ink-3">
          Documents in a collection are visible only to its members. Everything else is shared.
        </p>
        <form onSubmit={create} className="ml-auto flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="new collection name…"
            className="w-[190px] rounded-lg border border-line-strong bg-canvas px-3 py-1 text-xs placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <Button variant="primary" small type="submit" disabled={!name.trim()}>
            Create
          </Button>
        </form>
      </div>
      {error && <p className="px-4 pb-2 text-xs text-danger">{error}</p>}
      {collections.map((c) => (
        <CollectionRow key={c.id} collection={c} onChanged={onChanged} />
      ))}
    </Card>
  );
}

export default function LibraryPage() {
  const [docs, setDocs] = useState<DocumentRead[] | null>(null);
  const [collections, setCollections] = useState<CollectionRead[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const [uploadInto, setUploadInto] = useState<string>("");
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
    listCollections()
      .then(setCollections)
      .catch(() => setCollections([]));
  }, []);

  useEffect(() => {
    refresh();
    me()
      .then((u) => setIsAdmin(u.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, [refresh]);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(file, uploadInto || null);
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
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    }
  }

  const collectionName = (id: string | null) =>
    id ? (collections.find((c) => c.id === id)?.name ?? "restricted") : null;

  const visible =
    docs?.filter((d) => {
      if (filter === "all") return true;
      if (filter === "shared") return !d.collection_id;
      if (filter === "stale") return isStale(d);
      return d.collection_id === filter;
    }) ?? null;

  return (
    <div>
      <PageHead
        title="Library"
        desc="Everything the copilot can answer from. Scanned files are OCR’d; Office files are parsed; collections control who sees what."
      />

      {isAdmin && <CollectionsPanel collections={collections} onChanged={refresh} />}

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
          dragging
            ? "border-accent bg-accent-subtle"
            : "border-line-strong hover:border-accent hover:bg-accent-subtle"
        }`}
      >
        <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[10px] bg-accent-subtle text-accent">
          <Upload size={18} />
        </span>
        <span>
          <span className="block text-sm font-semibold">Drop files to upload, or browse</span>
          <span className="mt-0.5 block text-[12.5px] text-ink-2">
            pdf · docx / pptx / xlsx · png / jpg · md / txt — processed on this server, nothing
            leaves it
          </span>
        </span>
        <span className="ml-auto flex items-center gap-2.5" onClick={(e) => e.stopPropagation()}>
          {collections.length > 0 && (
            <select
              value={uploadInto}
              onChange={(e) => setUploadInto(e.target.value)}
              className="rounded-full border border-line bg-canvas px-3 py-1 text-xs text-ink-2 focus:outline-none"
            >
              <option value="">into: shared</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  into: {c.name}
                </option>
              ))}
            </select>
          )}
          {busy ? (
            <Spinner />
          ) : (
            <Button variant="primary" onClick={() => fileInput.current?.click()}>
              Upload
            </Button>
          )}
        </span>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.md,.txt,.docx,.pptx,.xlsx"
          className="hidden"
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {(collections.length > 0 || docs?.some(isStale)) && (
        <div className="mb-3.5 flex flex-wrap items-center gap-2">
          {[
            { key: "all", label: "All" },
            { key: "shared", label: "Shared" },
            { key: "stale", label: "Stale" },
            ...collections.map((c) => ({ key: c.id, label: c.name })),
          ].map((pill) => (
            <button
              key={pill.key}
              onClick={() => setFilter(pill.key)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                filter === pill.key
                  ? "border-ink bg-ink text-canvas"
                  : "border-line bg-canvas text-ink-2 hover:border-line-strong"
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="mb-4">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}

      <Card className="overflow-hidden">
        {visible === null ? (
          <TableSkeleton rows={5} />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No documents here"
            hint="Upload a document above — it becomes searchable in seconds."
          />
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="bg-subtle text-left text-xs font-semibold text-ink-2">
                <th className="px-4 py-2.5">Document</th>
                <th className="px-4 py-2.5">Collection</th>
                <th className="px-4 py-2.5">Extraction</th>
                <th className="px-4 py-2.5">Pages</th>
                <th className="px-4 py-2.5">Size</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Added</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {visible.map((doc) => (
                <tr
                  key={doc.id}
                  className="group border-t border-line transition-colors hover:bg-subtle"
                >
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2 font-semibold">
                      {doc.filename}
                      {doc.doc_metadata["knowledge_entry"] === true && (
                        <Pill tone="accent">agent note</Pill>
                      )}
                      {isStale(doc) && (
                        <Pill tone="warn" dot>
                          stale
                        </Pill>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {doc.collection_id ? (
                      <Pill tone="accent">{collectionName(doc.collection_id)}</Pill>
                    ) : (
                      <span className="text-xs text-ink-3">shared</span>
                    )}
                  </td>
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
                      <Button
                        variant="ghost"
                        small
                        className="text-danger"
                        onClick={() => void remove(doc)}
                      >
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
