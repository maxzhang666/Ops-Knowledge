import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import AgentCreate, AgentResponse, AgentUpdate
from app.agent.service import AgentService
from app.auth.dependencies import CurrentUser, check_resource_access
from app.auth.models import UserRole
from app.chat.prompt import (
    assemble_prompt,
    detect_required_vars,
    format_context_chunks,
)
from app.core.database import get_db
from app.core.dependencies import PaginatedResponse, PaginationParams
from app.department.service import DepartmentService

router = APIRouter(prefix="/agents", tags=["agents"])

_SEED_DIR = Path(__file__).resolve().parent.parent / "core" / "seed"


@router.get("/prompt-templates")
async def list_prompt_templates(current_user: CurrentUser):
    """Seed prompt templates for the Agent config UI template picker."""
    path = _SEED_DIR / "prompt_templates.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


class PreviewPromptRequest(BaseModel):
    query: str = "示例问题：你好，请介绍一下。"
    system_prompt: str | None = None  # override; defaults to agent's current prompt


@router.post("/{agent_id}/preview-prompt")
async def preview_prompt(
    agent_id: uuid.UUID,
    body: PreviewPromptRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Render the exact messages[] that would be sent to the LLM.

    Retrieval is simulated with placeholder content unless the query is
    non-empty AND the agent has KBs linked AND prompt contains {{context}}.
    """
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(current_user, "agent", agent.id, db, agent.created_by)

    template = body.system_prompt if body.system_prompt is not None else (agent.system_prompt or "")
    required = detect_required_vars(template)
    kb_ids = agent.knowledge_base_ids or []

    # Build fake-but-realistic context sample for preview
    context_str = ""
    if "context" in required:
        sample_chunks = [
            {"title": "示例文档 1", "content": "（这是预览时的样例内容，实际检索会替换为真实资料）"},
            {"title": "示例文档 2", "content": "（检索结果数量与 top_k 及 KB 内容相关）"},
        ] if kb_ids else []
        context_str = format_context_chunks(sample_chunks, max_tokens=2000)

    kb_names: list[str] = []
    if kb_ids:
        from app.knowledge.service import KnowledgeBaseService
        kb_svc = KnowledgeBaseService(db)
        for kid in kb_ids:
            try:
                kb = await kb_svc.get_kb(uuid.UUID(str(kid)))
                if kb:
                    kb_names.append(kb.name)
            except Exception:
                pass

    variables = {
        "context": context_str,
        "history_summary": "",
        "query": body.query,
        "knowledge_names": ", ".join(kb_names),
        "kb_count": str(len(kb_ids)),
    }

    messages = assemble_prompt(
        system_prompt=template,
        variables=variables,
        history=[],
        query=body.query,
    )
    return {
        "messages": messages,
        "detected_variables": sorted(required),
        "retrieval_will_trigger": "context" in required and bool(kb_ids),
    }


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.create_agent(data, current_user.id)
    return agent


@router.get("", response_model=PaginatedResponse)
async def list_agents(
    current_user: CurrentUser,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == UserRole.SYSTEM_ADMIN:
        accessible_ids = None
    else:
        dept_svc = DepartmentService(db)
        accessible_ids = await dept_svc.get_accessible_resource_ids(
            current_user.id, "agent"
        )
    svc = AgentService(db)
    items, total = await svc.list_agents(
        current_user.id, accessible_ids, pagination.offset, pagination.page_size
    )
    await svc.attach_share_flags(items, current_user.id)
    return PaginatedResponse(
        items=[AgentResponse.model_validate(i) for i in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by
    )
    await svc._attach_share_flag(agent, current_user.id)
    return agent


@router.post("/{agent_id}/update", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    data: AgentUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by, "edit"
    )
    return await svc.update_agent(agent_id, data, current_user.id)


@router.post("/{agent_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    svc = AgentService(db)
    agent = await svc.get_agent(agent_id)
    await check_resource_access(
        current_user, "agent", agent.id, db, agent.created_by, "full"
    )
    await svc.delete_agent(agent_id)
