"""Orchestrator Agent runtime (Plan 31).

Rule-driven router: user message → 3-step cascade (condition → keyword/
regex → LLM intent → default) → handler dispatch → unified event stream.

Entry point is ``service.OrchestratorService.route``; the chat pipeline
(``app/chat/orchestrator_pipeline.py``) owns conversation persistence
and SSE framing, this package owns the routing decision + handler
dispatch only.
"""
