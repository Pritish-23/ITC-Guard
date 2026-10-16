"""LangGraph orchestration for the deterministic and offline agent pipeline."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..llm.base import LLMProvider
from ..llm.mock import MockProvider
from ..matcher import reconcile
from ..models import ReconciliationReport
from ..settings import ReconciliationSettings
from .drafter import draft_supplier_messages
from .explainer import explain_mismatches
from .reviewer import review_drafts
from .resolver import resolve_matches
from .state import GraphState


def build_graph(provider: LLMProvider | None = None):
    """Build a compiled graph with the supplied provider, defaulting to the mock."""

    llm = provider or MockProvider()

    def ingest(state: GraphState) -> dict[str, Any]:
        return dict(state)

    def normalize(state: GraphState) -> dict[str, Any]:
        return dict(state)

    def match(state: GraphState) -> dict[str, Any]:
        if state.get("match_results") is not None:
            return dict(state)
        return {
            **state,
            "match_results": reconcile(
                state.get("books_invoices", []),
                state.get("gstr2b_invoices", []),
                state.get("settings", ReconciliationSettings()),
            ),
        }

    def router(state: GraphState) -> dict[str, Any]:
        return dict(state)

    def resolver(state: GraphState) -> dict[str, Any]:
        return dict(resolve_matches(dict(state), llm))

    def explainer(state: GraphState) -> dict[str, Any]:
        return dict(explain_mismatches(dict(state), llm))

    def drafter(state: GraphState) -> dict[str, Any]:
        return dict(draft_supplier_messages(dict(state), llm))

    def reviewer(state: GraphState) -> dict[str, Any]:
        return dict(review_drafts(dict(state), llm))

    def report(state: GraphState) -> dict[str, Any]:
        return {
            **state,
            "report": ReconciliationReport.from_results(
                state.get("match_results", []),
                state.get("drafts"),
            ),
        }

    nodes = {
        "ingest": ingest,
        "normalize": normalize,
        "match": match,
        "router": router,
        "resolver": resolver,
        "explainer": explainer,
        "drafter": drafter,
        "reviewer": reviewer,
        "report": report,
    }
    builder = StateGraph(GraphState)
    for name, node in nodes.items():
        builder.add_node(name, node)
    builder.add_edge(START, "ingest")
    names = tuple(nodes)
    for previous, current in zip(names, names[1:]):
        builder.add_edge(previous, current)
    builder.add_edge("report", END)
    return builder.compile()


def invoke_offline(
    state: GraphState | None = None,
    provider: LLMProvider | None = None,
) -> GraphState:
    """Run the complete pipeline without network access."""

    return build_graph(provider).invoke(state or {})


graph = build_graph()

__all__ = ["build_graph", "graph", "invoke_offline"]
