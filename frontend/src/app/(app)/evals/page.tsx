"use client";

/** Evals: golden-question datasets, live pipeline runs, metric history. */

import { FlaskConical, Play, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  addEvalCase,
  ApiError,
  createEvalDataset,
  deleteEvalDataset,
  getEvalDataset,
  listEvalDatasets,
  listEvalRuns,
  listProfiles,
  runEvalDataset,
} from "@/lib/api";
import type { EvalDatasetDetail, EvalDatasetRead, EvalRunRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, EmptyState, Pill, Spinner, TableSkeleton } from "@/components/ui";

const METRIC_LABELS: Record<string, string> = {
  hit_rate: "Hit rate",
  mrr: "MRR",
  page_hit_rate: "Page hits",
  keyword_recall: "Keyword recall",
  citation_accuracy: "Citations",
};

function MetricChips({ metrics }: { metrics: Record<string, number> }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {Object.entries(metrics).map(([key, value]) => (
        <Pill key={key} tone={value >= 0.9 ? "ok" : value >= 0.7 ? "warn" : "danger"}>
          {METRIC_LABELS[key] ?? key} {value.toFixed(2)}
        </Pill>
      ))}
    </span>
  );
}

function DatasetPanel({
  dataset,
  onDeleted,
}: {
  dataset: EvalDatasetRead;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = useState<EvalDatasetDetail | null>(null);
  const [runs, setRuns] = useState<EvalRunRead[]>([]);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [runProfile, setRunProfile] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [keywords, setKeywords] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    getEvalDataset(dataset.id)
      .then(setDetail)
      .catch(() => setDetail(null));
    listEvalRuns(dataset.id)
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [dataset.id]);

  useEffect(() => {
    refresh();
    listProfiles()
      .then((list) => setProfiles(list.map((p) => p.name)))
      .catch(() => setProfiles([]));
  }, [refresh]);

  async function addCase(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await addEvalCase(
        dataset.id,
        question.trim(),
        keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
      );
      setQuestion("");
      setKeywords("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the case.");
    }
  }

  async function run() {
    setRunning(true);
    setError(null);
    try {
      await runEvalDataset(dataset.id, runProfile || null);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Run failed.");
    } finally {
      setRunning(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete dataset “${dataset.name}” and its runs?`)) return;
    await deleteEvalDataset(dataset.id).catch(() => undefined);
    onDeleted();
  }

  return (
    <div className="min-w-0 flex-1">
      <Card className="mb-4 px-5 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-[15px] font-semibold">{dataset.name}</h2>
          {dataset.profile && <Pill tone="gray">{dataset.profile}</Pill>}
          <Pill tone="gray">{detail?.cases.length ?? "…"} cases</Pill>
          <span className="ml-auto flex items-center gap-2">
            {profiles.length > 0 && (
              <select
                value={runProfile}
                onChange={(e) => setRunProfile(e.target.value)}
                className="rounded-full border border-line bg-canvas px-3 py-1 text-xs text-ink-2 focus:outline-none"
              >
                <option value="">run with: dataset profile</option>
                {profiles.map((name) => (
                  <option key={name} value={name}>
                    run with: {name}
                  </option>
                ))}
              </select>
            )}
            <Button
              variant="primary"
              small
              disabled={running || !detail?.cases.length}
              onClick={() => void run()}
            >
              {running ? <Spinner /> : <Play size={13} />} Run
            </Button>
            <Button variant="ghost" small className="text-danger" onClick={() => void remove()}>
              <Trash2 size={13} />
            </Button>
          </span>
        </div>

        <form onSubmit={addCase} className="flex flex-wrap items-center gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="golden question, e.g. Who must wear a helmet?"
            required
            className="min-w-[260px] flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-1.5 text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <input
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="expected keywords, comma-separated"
            className="min-w-[220px] rounded-lg border border-line-strong bg-canvas px-3 py-1.5 text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <Button small type="submit" disabled={!question.trim()}>
            <Plus size={13} /> Add case
          </Button>
        </form>

        {error && (
          <div className="mt-3">
            <Callout tone="warn" icon="⚠">
              {error}
            </Callout>
          </div>
        )}

        <div className="mt-3 flex flex-col gap-1">
          {detail?.cases.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <span className="text-ink">{c.question}</span>
              {c.expected_keywords.map((k) => (
                <span key={k} className="rounded-full bg-subtle px-2 font-mono text-[10.5px] text-ink-2">
                  {k}
                </span>
              ))}
            </div>
          ))}
          {detail !== null && detail.cases.length === 0 && (
            <p className="text-[12.5px] text-ink-3">
              No cases yet — add the questions your users actually ask, with the words a correct
              answer must contain.
            </p>
          )}
        </div>
      </Card>

      <Card className="overflow-hidden">
        {runs.length === 0 ? (
          <EmptyState title="No runs yet" hint="Run the dataset to measure the live pipeline." />
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="bg-subtle text-left text-xs font-semibold text-ink-2">
                <th className="px-4 py-2.5">Run</th>
                <th className="px-4 py-2.5">Profile</th>
                <th className="px-4 py-2.5">Cases</th>
                <th className="px-4 py-2.5">Metrics</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-t border-line align-top">
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {new Date(run.created_at).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-3">
                    <Pill tone="gray">{run.profile}</Pill>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">{run.case_count}</td>
                  <td className="px-4 py-3">
                    <MetricChips metrics={run.metrics} />
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

export default function EvalsPage() {
  const [datasets, setDatasets] = useState<EvalDatasetRead[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listEvalDatasets()
      .then((list) => {
        setDatasets(list);
        setSelected((current) => current ?? list[0]?.id ?? null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setError("Evaluations require the admin role.");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not reach the server.");
        }
      });
  }, []);

  useEffect(refresh, [refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      const dataset = await createEvalDataset(name.trim(), null);
      setName("");
      setSelected(dataset.id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the dataset.");
    }
  }

  const active = datasets?.find((d) => d.id === selected) ?? null;

  return (
    <div>
      <PageHead
        title="Evaluations"
        desc="Golden question sets run against the live pipeline — measure quality before trusting a change, and A/B profiles on the same questions."
      />

      {error && (
        <Callout tone="warn" icon="⚠">
          {error}
        </Callout>
      )}

      {!error && (
        <div className="flex gap-6 max-md:flex-col">
          <aside className="w-[240px] shrink-0">
            <form onSubmit={create} className="mb-3 flex items-center gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="new dataset name…"
                className="min-w-0 flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-1.5 text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
              />
              <Button variant="primary" small type="submit" disabled={!name.trim()}>
                <Plus size={13} />
              </Button>
            </form>
            {datasets === null ? (
              <TableSkeleton rows={3} />
            ) : (
              datasets.map((dataset) => (
                <button
                  key={dataset.id}
                  onClick={() => setSelected(dataset.id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                    selected === dataset.id
                      ? "bg-subtle font-semibold"
                      : "text-ink-2 hover:bg-subtle"
                  }`}
                >
                  <FlaskConical size={13} className="shrink-0 text-ink-3" />
                  <span className="truncate">{dataset.name}</span>
                </button>
              ))
            )}
            {datasets !== null && datasets.length === 0 && (
              <p className="px-2.5 text-[12px] text-ink-3">No datasets yet.</p>
            )}
          </aside>

          {active ? (
            <DatasetPanel
              key={active.id}
              dataset={active}
              onDeleted={() => {
                setSelected(null);
                refresh();
              }}
            />
          ) : (
            datasets !== null &&
            datasets.length === 0 && (
              <Card className="flex-1">
                <EmptyState
                  title="Create your first golden set"
                  hint="5–10 real questions with expected keywords is enough to catch regressions."
                />
              </Card>
            )
          )}
        </div>
      )}
    </div>
  );
}
