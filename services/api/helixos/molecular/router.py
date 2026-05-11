"""Molecular biology API routes."""

from fastapi import APIRouter, Depends

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.molecular.schemas import Sequence
from helixos.molecular.service import sequence_service

router = APIRouter(prefix="/sequences", tags=["molecular"])


@router.get("/{sequence_id}", response_model=Sequence)
def get_sequence(sequence_id: str, actor: Actor = Depends(get_current_actor)) -> Sequence:
    """Fetch sequence metadata visible to the authenticated caller."""
    return sequence_service.get_sequence(sequence_id=sequence_id, actor=actor)
