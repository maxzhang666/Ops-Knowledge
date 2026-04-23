"""Node registry HTTP API — GET only. Frontend Node Palette + Config Panel
consume this to auto-render the editor."""
from fastapi import APIRouter, HTTPException

from app.auth.dependencies import CurrentUser
from app.workflow.nodes.registry import registry

router = APIRouter(prefix="/workflow/nodes", tags=["workflow-nodes"])


@router.get("/registry")
async def get_node_registry(user: CurrentUser, group: bool = False):
    """Full node catalog. Pass `?group=true` to receive entries grouped by
    category (ordered by canonical CATEGORY_ORDER); default flat."""
    if group:
        return {"groups": registry.grouped_catalog()}
    return {"nodes": registry.catalog()}


@router.get("/{node_type}")
async def get_node_detail(node_type: str, user: CurrentUser, version: str = "1.0"):
    try:
        cls = registry.get(node_type, version)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown node: {node_type}@{version}")
    return {
        "manifest": cls.manifest.model_dump(),
        "io": cls.io.model_dump(),
        "config_form": cls.config_form.model_dump(by_alias=True),
    }
