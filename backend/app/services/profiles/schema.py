"""RAG profile schema — the declarative spine of the pipeline.

A profile is a validated configuration pack that tunes every stage of the
pipeline (chunking, retrieval, generation, provider selection) for a domain.
Domain packs live as YAML in ``packs/``; the pipeline reads *only* from the
active profile, never from hardcoded values.

Validation is strict (``extra="forbid"``): a typo in a YAML pack fails at load
time, not silently at query time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChunkingConfig(_StrictModel):
    """How documents are split before embedding."""

    strategy: Literal["semantic", "fixed"] = "semantic"
    # Characters, not tokens — deterministic across tokenizers.
    chunk_size: int = Field(default=1200, ge=100, le=8000)
    chunk_overlap: int = Field(default=150, ge=0)
    respect_page_boundaries: bool = True

    @model_validator(mode="after")
    def _overlap_below_size(self) -> ChunkingConfig:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self


class RetrievalConfig(_StrictModel):
    """Hybrid retrieval and reranking behavior."""

    # Candidates fetched per channel before fusion. Wider nets help recall;
    # the reranker restores precision.
    dense_top_k: int = Field(default=30, ge=1, le=200)
    sparse_top_k: int = Field(default=30, ge=1, le=200)
    fusion: Literal["rrf"] = "rrf"
    # Standard RRF constant; higher dampens rank-position dominance.
    rrf_k: int = Field(default=60, ge=1)
    rerank_enabled: bool = True
    # Chunks handed to the LLM after fusion/reranking.
    final_top_n: int = Field(default=8, ge=1, le=50)
    # Optional similarity floor; candidates below it are dropped pre-fusion.
    min_dense_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class GenerationConfig(_StrictModel):
    """Grounded answer generation and trust thresholds."""

    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=64, le=32000)
    # When true, an answer without at least one citation is rejected.
    citations_required: bool = True
    groundedness_check: bool = True
    # Confidence in [0, 1]. Below review -> flagged for human review;
    # below refuse -> the system declines to answer.
    confidence_threshold_review: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_threshold_refuse: float = Field(default=0.25, ge=0.0, le=1.0)
    # Optional domain-specific system prompt override.
    system_prompt: str | None = None

    @model_validator(mode="after")
    def _refuse_below_review(self) -> GenerationConfig:
        if self.confidence_threshold_refuse > self.confidence_threshold_review:
            raise ValueError(
                "confidence_threshold_refuse must not exceed confidence_threshold_review."
            )
        return self


class ProvidersConfig(_StrictModel):
    """Provider overrides. ``None`` inherits the deployment default."""

    parser: str | None = None
    embedder: str | None = None
    vector_store: str | None = None
    reranker: str | None = None
    llm: str | None = None


class RagProfile(_StrictModel):
    """A complete, validated pipeline configuration for one domain."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,40}$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    industry: str | None = None
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
