"""LangGraph-backed workflow execution engine.

Replaces the in-house `app/workflow/scheduler.py` behind a feature flag.
See `docs/superpowers/specs/ops-knowledge/02-workflow-engine.md` §Execution
Engine Migration and Plan 29 for the full design and phased delivery plan.

Phase 1 skeleton — module layout:

- ``state`` – ``WorkflowState`` TypedDict + merge reducers
- ``compiler`` – DSL → LangGraph ``StateGraph``
- ``node_adapters`` – our ``AbstractNode`` → LangGraph-compatible callables
- ``events`` – translate LangGraph ``astream_events`` into our ``EventBus``
- ``streaming`` – ``StreamWriter`` helpers for nodes that emit chunks
"""
