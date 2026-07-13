"use client";

/** Ask — Intelligence Reports: streamed grounded answers with citations,
 *  confidence sub-scores, feedback, and a persistent sources rail. Thread
 *  history and "New Analysis" live in the app shell and hand actions over
 *  via readAskAction(). */

import Link from "next/link";
import {
  ArrowUp,
  ChevronDown,
  FileSearch,
  Layers,
  Mic,
  Paperclip,
  Share2,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import {
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";

import {
  ApiError,
  createThread,
  getThread,
  listProfiles,
  streamQuery,
  submitFeedback,
  uploadDocument,
} from "@/lib/api";
import type { QueryCitation, QueryResponse } from "@/lib/types";
import { readAskAction } from "@/components/shell";
import { Callout, Cite, Spinner } from "@/components/ui";

interface Exchange {
  question: string;
  at: string;
  response: QueryResponse | null;
  error: string | null;
  streaming: string;
}

/** Render answer text with [n] markers as citation chips. */
function AnswerText({ text }: { text: string }) {
  const parts = text.split(/\[(\d{1,2})\]/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <Cite key={i} marker={Number(part)} /> : <Fragment key={i}>{part}</Fragment>,
      )}
    </>
  );
}

function confidenceTone(value: number): string {
  if (value >= 0.8) return "bg-ok-subtle text-ok";
  if (value >= 0.5) return "bg-warn-subtle text-warn";
  return "bg-danger-subtle text-danger";
}

function timeLabel(iso: string): string {
  const date = new Date(iso);
  const time = date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (date.toDateString() === new Date().toDateString()) return `Today, ${time}`;
  return `${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${time}`;
}

function SubScores({ breakdown }: { breakdown: Record<string, number> }) {
  const retrieval = breakdown["retrieval"];
  const grounded = breakdown["groundedness"];
  if (retrieval === undefined && grounded === undefined) return null;
  return (
    <span className="font-mono text-[10.5px] text-ink-3">
      {retrieval !== undefined && <>R: {Math.round(retrieval * 100)}%</>}
      {retrieval !== undefined && grounded !== undefined && <> · </>}
      {grounded !== undefined && <>G: {Math.round(grounded * 100)}%</>}
    </span>
  );
}

function IntelligenceReport({ response }: { response: QueryResponse }) {
  const [verdict, setVerdict] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function rate(value: "helpful" | "unhelpful") {
    setVerdict(value);
    await submitFeedback(response.query_id, value).catch(() => setVerdict(null));
  }

  function share() {
    const sources = response.citations
      .map((c) => `[${c.marker}] ${c.filename}${c.page_number != null ? `, p.${c.page_number}` : ""}`)
      .join("\n");
    void navigator.clipboard.writeText(
      `${response.answer ?? ""}\n\nSources:\n${sources}\n\nConfidence: ${response.confidence.toFixed(2)}`,
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (!response.answered || !response.answer) {
    return (
      <div className="mb-2 max-w-[640px]">
        <Callout tone="danger" icon="✕">
          <b>Declined.</b> The corpus does not support an answer to this question
          {response.refusal_reason && (
            <>
              {" "}
              (<code className="font-mono text-xs">{response.refusal_reason}</code>)
            </>
          )}
          . No answer is safer than a wrong one.
        </Callout>
      </div>
    );
  }

  return (
    <div className="animate-rise mb-2 rounded-xl border border-line bg-canvas shadow-md">
      <div className="flex flex-wrap items-center gap-2.5 border-b border-line-soft border-b-line px-5 py-3">
        <span className="grid h-6 w-6 place-items-center rounded-[7px] bg-accent-subtle text-accent">
          <ShieldCheck size={14} />
        </span>
        <span className="text-[13.5px] font-semibold tracking-[-0.01em]">Intelligence Report</span>
        <span className="ml-auto flex items-center gap-2.5">
          <SubScores breakdown={response.confidence_breakdown} />
          <span
            className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-bold ${confidenceTone(response.confidence)}`}
          >
            Confidence: {Math.round(response.confidence * 100)}%
          </span>
        </span>
      </div>

      <div className="px-5 py-4">
        <p className="max-w-[680px] text-[14.5px] leading-[1.75]">
          <AnswerText text={response.answer} />
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-5 py-2.5">
        <button
          onClick={() => void rate("helpful")}
          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
            verdict === "helpful" ? "bg-ok-subtle text-ok" : "text-ink-2 hover:bg-subtle"
          }`}
        >
          <ThumbsUp size={13} /> Helpful
        </button>
        <button
          onClick={() => void rate("unhelpful")}
          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
            verdict === "unhelpful" ? "bg-danger-subtle text-danger" : "text-ink-2 hover:bg-subtle"
          }`}
        >
          <ThumbsDown size={13} /> Unhelpful
        </button>
        <button
          onClick={share}
          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-ink-2 transition-colors hover:bg-subtle"
        >
          <Share2 size={13} /> {copied ? "Copied" : "Share"}
        </button>
        {response.took_ms > 0 && (
          <span className="ml-auto font-mono text-[10.5px] text-ink-3">
            {response.profile} · {Math.round(response.took_ms)} ms
          </span>
        )}
      </div>
    </div>
  );
}

function SourcesRail({
  citations,
  onClose,
}: {
  citations: QueryCitation[];
  onClose: () => void;
}) {
  return (
    <aside className="sticky top-[76px] w-[290px] shrink-0 max-lg:hidden">
      <div className="rounded-xl border border-line bg-canvas shadow-sm">
        <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <FileSearch size={13} className="text-ink-3" />
          <span className="font-mono text-[10.5px] font-semibold tracking-[0.14em] text-ink-2 uppercase">
            Sources ({citations.length})
          </span>
          <button onClick={onClose} className="ml-auto text-ink-3 hover:text-ink" title="Hide">
            <X size={14} />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2.5">
          {citations.map((citation, index) => (
            <Link
              key={citation.marker}
              href={`/viewer/?doc=${citation.document_id}&chunk=${citation.chunk_id}`}
              className={`mb-2 block rounded-lg border px-3 py-2.5 transition-colors last:mb-0 ${
                index === 0
                  ? "border-accent-border bg-accent-subtle"
                  : "border-line hover:border-accent-border"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="grid h-[18px] min-w-[18px] place-items-center rounded-[5px] bg-accent font-mono text-[10px] font-bold text-white">
                  {citation.marker}
                </span>
                <span className="truncate font-mono text-[11px] font-semibold">
                  {citation.filename}
                </span>
              </span>
              {citation.page_number != null && (
                <span className="mt-1 block font-mono text-[10px] text-ink-3">
                  Page {citation.page_number}
                </span>
              )}
              <span className="mt-1 line-clamp-3 text-[11.5px] leading-normal text-ink-2 italic">
                “{citation.snippet}”
              </span>
            </Link>
          ))}
        </div>
        <div className="border-t border-line p-2.5">
          <Link
            href="/library"
            className="block rounded-lg py-1.5 text-center text-xs font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink"
          >
            Open Full Library
          </Link>
        </div>
      </div>
    </aside>
  );
}

// ---- dictation (browser Web Speech API; button renders only if supported) ----

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  onresult: ((event: SpeechResultEventLike) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

interface SpeechResultEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

const STARTERS = [
  "Summarize the key points of our most recent document",
  "What deadlines or obligations should we be aware of?",
  "Where do our documents contradict each other?",
];

function speechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export default function AskPage() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState("");
  const [profiles, setProfiles] = useState<string[]>([]);
  const [profile, setProfile] = useState<string | null>(null);
  const [activeThread, setActiveThread] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(false);
  const micSupported = useSyncExternalStore(
    () => () => undefined,
    () => speechRecognitionCtor() !== null,
    () => false,
  );
  const [profileOpen, setProfileOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);

  // Grow the composer with its content (capped by max-h on the textarea).
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`;
  }, [question]);

  useEffect(() => {
    listProfiles()
      .then((list) => setProfiles(list.map((p) => p.name)))
      .catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges]);

  const openThread = useCallback(async (id: string) => {
    setActiveThread(id);
    try {
      const detail = await getThread(id);
      setExchanges(
        detail.messages.map((m) => ({
          question: m.query,
          at: m.created_at,
          streaming: "",
          error: null,
          response: {
            query_id: m.id,
            query: m.query,
            profile: "",
            answer: m.answer,
            answered: m.answered,
            refusal_reason: m.refusal_reason,
            citations: m.citations as unknown as QueryResponse["citations"],
            confidence: m.confidence,
            confidence_breakdown: {},
            grounded_ratio: 0,
            needs_review: m.needs_review,
            model: "",
            sources_considered: 0,
            retrieval_took_ms: 0,
            took_ms: 0,
          },
        })),
      );
    } catch {
      setExchanges([]);
    }
  }, []);

  // The shell's "+ New Analysis" button and history menu hand actions over here.
  useEffect(() => {
    const handle = () => {
      const action = readAskAction();
      if (action === "new") {
        setActiveThread(null);
        setExchanges([]);
      } else if (action?.startsWith("thread:")) {
        void openThread(action.slice(7));
      }
    };
    handle();
    window.addEventListener("ekc-ask-action", handle);
    return () => window.removeEventListener("ekc-ask-action", handle);
  }, [openThread]);

  const latest = [...exchanges].reverse().find((e) => e.response?.answered);
  const railCitations = latest?.response?.citations ?? [];
  const flagged = [...exchanges].reverse().find((e) => e.response)?.response?.needs_review;

  function toggleMic() {
    if (micOn) {
      recRef.current?.stop();
      return;
    }
    const Ctor = speechRecognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = false;
    rec.onresult = (event) => {
      const transcript = Array.from(
        { length: event.results.length },
        (_, i) => event.results[i]?.[0]?.transcript ?? "",
      )
        .join(" ")
        .trim();
      if (transcript) setQuestion((q) => (q ? `${q} ${transcript}` : transcript));
    };
    rec.onend = () => setMicOn(false);
    recRef.current = rec;
    setMicOn(true);
    rec.start();
  }

  async function attach(files: FileList | null) {
    if (!files?.length) return;
    setUploadNote("Uploading…");
    try {
      for (const file of Array.from(files)) await uploadDocument(file, null);
      setUploadNote(`Added ${files.length} document${files.length > 1 ? "s" : ""} to the library`);
    } catch (err) {
      setUploadNote(err instanceof ApiError ? err.message : "Upload failed.");
    }
    setTimeout(() => setUploadNote(null), 3000);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setExchanges((prev) => [
      ...prev,
      { question: q, at: new Date().toISOString(), response: null, error: null, streaming: "" },
    ]);
    try {
      let threadId = activeThread;
      if (!threadId) {
        threadId = (await createThread()).id;
        setActiveThread(threadId);
      }
      const response = await streamQuery(q, profile, threadId, (text) =>
        setExchanges((prev) =>
          prev.map((e, i) => (i === prev.length - 1 ? { ...e, streaming: e.streaming + text } : e)),
        ),
      );
      setExchanges((prev) =>
        prev.map((e, i) => (i === prev.length - 1 ? { ...e, response, streaming: "" } : e)),
      );
      setRailOpen(true);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not reach the server.";
      setExchanges((prev) =>
        prev.map((e, i) => (i === prev.length - 1 ? { ...e, error: message } : e)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-start gap-7">
      {/* ——— Conversation, centered ——— */}
      <div className="mx-auto w-full max-w-[720px] min-w-0">
        {flagged && (
          <div className="mb-5 flex items-center gap-2.5 rounded-lg border border-warn/30 bg-warn-subtle px-4 py-2.5 text-[12.5px]">
            <ShieldCheck size={14} className="shrink-0 text-warn" />
            <span>
              This response is below the confidence threshold and is{" "}
              <b>queued for Human Review</b>.
            </span>
            <Link
              href="/review"
              className="ml-auto shrink-0 font-semibold text-warn hover:underline"
            >
              View details
            </Link>
          </div>
        )}

        {exchanges.length === 0 && (
          <div className="animate-rise pt-16 pb-12 text-center">
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-2xl bg-accent-subtle text-accent">
              <ShieldCheck size={20} />
            </span>
            <h1 className="mt-4 text-[26px] font-bold tracking-[-0.02em]">Ask your documents</h1>
            <p className="mx-auto mt-2 max-w-[440px] text-sm text-ink-2">
              Every report cites its sources and carries a confidence score. When the evidence
              isn&rsquo;t there, it declines.
            </p>
            <div className="mt-7 flex flex-wrap justify-center gap-2">
              {STARTERS.map((starter) => (
                <button
                  key={starter}
                  onClick={() => {
                    setQuestion(starter);
                    inputRef.current?.focus();
                  }}
                  className="rounded-full border border-line bg-canvas px-3.5 py-1.5 text-[12.5px] text-ink-2 shadow-sm transition-all hover:border-accent-border hover:text-ink hover:shadow-md"
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
        )}

        {exchanges.map((exchange, i) => {
          const previous = exchanges[i - 1];
          const showTime =
            !previous ||
            new Date(exchange.at).getTime() - new Date(previous.at).getTime() > 5 * 60_000;
          return (
            <div key={i} className="mb-6">
              {showTime && (
                <p className="mb-4 text-center font-mono text-[10.5px] text-ink-3">
                  {timeLabel(exchange.at)}
                </p>
              )}
              <div className="animate-rise mb-4 flex justify-end">
                <p className="max-w-[75%] rounded-[14px_14px_4px_14px] border border-line bg-canvas px-4 py-2.5 text-sm shadow-sm">
                  {exchange.question}
                </p>
              </div>
              {exchange.streaming && !exchange.response && (
                <p className="max-w-[680px] text-[14.5px] leading-[1.75]">
                  <AnswerText text={exchange.streaming} />
                  <span className="ml-0.5 inline-block h-[15px] w-[7px] animate-pulse bg-accent align-middle" />
                </p>
              )}
              {exchange.response && (
                <>
                  <IntelligenceReport response={exchange.response} />
                  <p className="font-mono text-[10.5px] text-ink-3">Knowledge Copilot · just now</p>
                </>
              )}
              {exchange.error && (
                <div className="max-w-[640px]">
                  <Callout tone="warn" icon="⚠">
                    {exchange.error}
                  </Callout>
                </div>
              )}
              {!exchange.response && !exchange.error && !exchange.streaming && (
                <div className="flex items-center gap-2.5 text-sm text-ink-3">
                  <Spinner /> Searching the corpus…
                </div>
              )}
            </div>
          );
        })}
        <div ref={endRef} />

        {/* ——— Composer ——— */}
        <form
          ref={formRef}
          onSubmit={submit}
          className="sticky bottom-4 mt-8 rounded-2xl border border-line-strong bg-canvas shadow-lg"
        >
          <textarea
            ref={inputRef}
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                formRef.current?.requestSubmit();
              }
            }}
            placeholder={micOn ? "Listening…" : "Ask anything about your knowledge base…"}
            className="block max-h-44 w-full resize-none bg-transparent px-5 pt-4 text-[15px] leading-relaxed placeholder:text-ink-3 focus:outline-none"
          />
          <div className="flex items-center gap-1 px-3 pt-1 pb-3">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="grid h-9 w-9 place-items-center rounded-full text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
              title="Add a document to the library"
            >
              <Paperclip size={16} />
            </button>
            {micSupported && (
              <button
                type="button"
                onClick={toggleMic}
                className={`grid h-9 w-9 place-items-center rounded-full transition-colors ${
                  micOn
                    ? "animate-pulse bg-danger-subtle text-danger"
                    : "text-ink-3 hover:bg-subtle hover:text-ink"
                }`}
                title={micOn ? "Stop dictation" : "Dictate your question"}
              >
                <Mic size={16} />
              </button>
            )}
            {profiles.length > 0 && (
              <div className="relative ml-1">
                <button
                  type="button"
                  onClick={() => setProfileOpen((v) => !v)}
                  className="flex items-center gap-1.5 rounded-full border border-line bg-subtle px-3 py-1.5 text-[12px] font-medium text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
                  title="Choose a retrieval profile"
                >
                  <Layers size={12} className="text-ink-3" />
                  {profile ?? "default"}
                  <ChevronDown size={12} className="text-ink-3" />
                </button>
                {profileOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setProfileOpen(false)} />
                    <div className="absolute bottom-[calc(100%+8px)] left-0 z-50 w-[200px] rounded-xl border border-line bg-canvas p-1.5 shadow-lg">
                      <p className="px-2.5 pt-1.5 pb-1 font-mono text-[10px] tracking-[0.12em] text-ink-3 uppercase">
                        Target profile
                      </p>
                      {[null, ...profiles].map((name) => (
                        <button
                          key={name ?? "default"}
                          type="button"
                          onClick={() => {
                            setProfile(name);
                            setProfileOpen(false);
                          }}
                          className={`flex w-full items-center rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                            profile === name
                              ? "bg-accent-subtle font-semibold text-accent"
                              : "hover:bg-subtle"
                          }`}
                        >
                          {name ?? "default"}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
            <span className="mx-2 hidden min-w-0 flex-1 truncate text-center font-mono text-[10px] text-ink-3 sm:block">
              {uploadNote ?? "Answers are grounded in your documents and always cite their sources."}
            </span>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.md,.txt,.docx,.pptx,.xlsx"
              className="hidden"
              onChange={(e) => {
                void attach(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              type="submit"
              disabled={busy || !question.trim()}
              title="Ask (Enter)"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-white shadow-sm transition-all hover:bg-accent-hover active:translate-y-px disabled:opacity-40"
            >
              <ArrowUp size={16} />
            </button>
          </div>
        </form>
      </div>

      {/* ——— Sources rail ——— */}
      {railOpen && railCitations.length > 0 && (
        <SourcesRail citations={railCitations} onClose={() => setRailOpen(false)} />
      )}
    </div>
  );
}
