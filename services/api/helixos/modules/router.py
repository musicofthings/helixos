"""Module registry routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor

router = APIRouter(tags=["modules"])


class ModuleInfo(BaseModel):
    """Public module metadata exposed to clients and agents."""

    id: str
    name: str
    phase: int
    enabled: bool
    description: str


MODULES: tuple[ModuleInfo, ...] = (
    ModuleInfo(id="auth", name="Authentication & Organizations", phase=1, enabled=True, description="Tenancy, users, workspaces, RBAC, and SSO-ready auth."),
    ModuleInfo(id="eln", name="Electronic Lab Notebook", phase=1, enabled=True, description="Experiments, protocols, blocks, signatures, and audit trail."),
    ModuleInfo(id="molecular", name="Molecular Biology Workspace", phase=1, enabled=True, description="Sequences, plasmids, annotations, and analysis."),
    ModuleInfo(id="inventory", name="Inventory & Reagents", phase=1, enabled=True, description="Reagents, lots, stock, expiry, and vendors."),
    ModuleInfo(id="ai", name="AI Copilot Layer", phase=1, enabled=True, description="Provider abstraction and lab copilots."),
    ModuleInfo(id="mcp", name="MCP Connector Framework", phase=1, enabled=True, description="Scientific tool connector registry and scoped execution."),
    ModuleInfo(id="cloning", name="Cloning Workflow Engine", phase=2, enabled=False, description="Assembly design, virtual gels, and construct lineage."),
    ModuleInfo(id="biobank", name="Biobank Management", phase=2, enabled=False, description="Samples, aliquots, storage, genealogy, and chain of custody."),
    ModuleInfo(id="workflows", name="Workflow Automation Engine", phase=2, enabled=False, description="SOP execution, approvals, tasks, and triggers."),
)


@router.get("/modules", response_model=list[ModuleInfo])
def list_modules(_actor: Actor = Depends(get_current_actor)) -> list[ModuleInfo]:
    """Return the HelixOS module roadmap and enabled status."""
    return list(MODULES)
