"use client";

/** Document viewer: chunks in reading order, cited chunk highlighted.
 *  Static-export friendly: /viewer/?doc=<id>&chunk=<id>. */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { ApiError, getDocument, listChunks } from "@/lib/api";
import type { ChunkRead, DocumentRead } from "@/lib/types";
import { Callout, Card, Pill, Spinner } from "@/components/ui";

function Viewer() {
  const params = useSearchParams();
  const docId = params.get("doc");
  const targetChunk = params.get("chunk");

  const [doc, setDoc] = useState<DocumentRead | null>(null);
  const [chunks, setChunks] = useState<ChunkRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const targetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!docId) return;
    Promise.all([getDocument(docId), listChunks(docId)])
      .then(([d, c]) => {
        setDoc(d);
        setChunks(c);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server."),
      );
  }, [docId]);

  useEffect(() => {
    if (chunks && targetChunk) {
      targetRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [chunks, targetChunk]);

  if (!docId || error) {
    return (
      <Callout tone="warn" icon="⚠">
        {error ?? "No document selected. Open a document from the Library or a citation."}
      </Callout>
    );
  }
  if (!doc || !chunks) {
    return (
      <div className="flex justify-center py-14">
        <Spinner />
      </div>
    );
  }

  const rows = chunks.map((chunk, i) => ({
    chunk,
    showPage: i === 0 || chunk.page_number !== chunks[i - 1].page_number,
  }));

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-[15px] font-semibold">{doc.filename}</h1>
        <Pill tone="gray">{doc.page_count != null ? `${doc.page_count} pages` : "no pages"}</Pill>
        <Pill tone="gray">{chunks.length} chunks</Pill>
        {doc.status === "completed" ? (
          <Pill tone="ok" dot>
            Ingested
          </Pill>
        ) : (
          <Pill tone="warn" dot>
            {doc.status}
          </Pill>
        )}
      </header>

      <div className="mx-auto max-w-[760px]">
        {rows.map(({ chunk, showPage }) => {
          const isTarget = chunk.id === targetChunk;
          return (
            <div key={chunk.id} ref={isTarget ? targetRef : undefined}>
              {showPage && chunk.page_number != null && (
                <p className="mt-6 mb-2 font-mono text-[11px] font-semibold tracking-wide text-ink-3">
                  PAGE {chunk.page_number}
                </p>
              )}
              <Card
                className={`mb-2.5 px-5 py-4 ${
                  isTarget ? "border-accent shadow-[0_0_0_3px_var(--accent-subtle)]" : ""
                }`}
              >
                <div className="mb-1.5 flex items-center gap-2 font-mono text-[10.5px] text-ink-3">
                  <span className="font-semibold text-ink-2">chunk {chunk.chunk_index}</span>
                  {chunk.token_count != null && <span>· {chunk.token_count} tokens</span>}
                  {isTarget && (
                    <span className="ml-auto">
                      <Pill tone="accent">Cited passage</Pill>
                    </span>
                  )}
                </div>
                <p className="text-[13.5px] leading-relaxed whitespace-pre-wrap">
                  {chunk.content}
                </p>
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ViewerPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-14">
          <Spinner />
        </div>
      }
    >
      <Viewer />
    </Suspense>
  );
}
