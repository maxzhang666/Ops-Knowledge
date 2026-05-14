"""Central ORM registry — eager-load every Base subclass.

Cross-model foreign keys (e.g. ``cost_records.user_id → users.id``,
``agents.created_by → users.id``) require every ``Base`` subclass to be
registered with SQLAlchemy's mapper registry **before any session flush**.
Otherwise a flush triggers ``Foreign key ... could not find table 'users'``
during relationship resolution, leaving the session in ``DEACTIVE`` state.

Importing this module is a side-effect-only act of "registering all models".
It MUST be imported by every entrypoint that opens DB sessions:
    - FastAPI app (``app/main.py`` — already covers via router imports)
    - Celery worker (``app/core/celery.py``)
    - Alembic migrations (``alembic/env.py``)

Adding a new ``models.py``? Add it here.
"""
# Ordering does not matter — SQLAlchemy resolves cross-table FKs lazily once
# all classes are registered. Grouped by domain for readability only.

from app.auth import models as _auth  # noqa: F401
from app.department import models as _dept  # noqa: F401
from app.system import models as _system  # noqa: F401

from app.model import models as _model  # noqa: F401

from app.knowledge import models as _kb  # noqa: F401
from app.knowledge.coverage import models as _kb_cov  # noqa: F401
from app.knowledge.evaluation import models as _kb_eval  # noqa: F401
from app.knowledge.evaluation import golden_models as _kb_eval_golden  # noqa: F401
from app.knowledge.governance import models as _kb_gov  # noqa: F401
from app.knowledge.retrieval import models as _kb_ret  # noqa: F401
from app.knowledge.tagging import models as _kb_tag  # noqa: F401

from app.agent import models as _agent  # noqa: F401
from app.agent.orchestrator import models as _orch  # noqa: F401
from app.mcp import models as _mcp  # noqa: F401
from app.chat import models as _chat  # noqa: F401

from app.workflow import models as _workflow  # noqa: F401
