"""Application service for molecular biology records."""

from datetime import datetime, timezone

from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.errors import api_error
from helixos.molecular.schemas import MoleculeType, Sequence, SequenceFeature, Topology

SEQUENCES: tuple[Sequence, ...] = (
    Sequence(
        id="seq_demo_reporter",
        organization_id="org_demo",
        name="Reporter plasmid backbone",
        molecule_type=MoleculeType.DNA,
        topology=Topology.CIRCULAR,
        length=5384,
        features=[
            SequenceFeature(name="CMV promoter", start=104, end=681, kind="promoter"),
            SequenceFeature(name="GFP", start=920, end=1639, kind="CDS"),
        ],
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    ),
    Sequence(
        id="seq_qc_amplicon",
        organization_id="org_qc",
        name="QC amplicon control",
        molecule_type=MoleculeType.DNA,
        topology=Topology.LINEAR,
        length=412,
        features=[SequenceFeature(name="Target amplicon", start=0, end=412, kind="amplicon")],
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    ),
)


class SequenceService:
    """Coordinates sequence use cases."""

    def get_sequence(self, sequence_id: str, actor: Actor) -> Sequence:
        """Fetch a sequence visible to the authenticated actor."""
        sequence = next((item for item in SEQUENCES if item.id == sequence_id), None)
        if sequence is None:
            raise api_error(status_code=404, code="not_found", message="Sequence not found")

        organization_service.require_access(actor, sequence.organization_id)
        return sequence


sequence_service = SequenceService()
