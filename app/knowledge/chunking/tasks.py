"""Celery autodiscover entry for the chunking package.

``celery_app.autodiscover_tasks([...])`` only imports each package's
``tasks`` submodule by default. Tasks living in differently-named files
(here: ``raptor_task.py``) are otherwise never imported by the worker
process and ``@shared_task`` registration never fires — the worker then
rejects messages with ``Received unregistered task of type ...``.

Importing the submodule here triggers its ``@shared_task`` decorators,
so the worker registers ``build_raptor_for_document`` and friends at
boot. Renaming ``raptor_task.py`` would also work, but would invalidate
the explicit ``name=`` in ``@shared_task`` and any messages already
queued under that name would be unconsumable.
"""
from app.knowledge.chunking import raptor_task  # noqa: F401
