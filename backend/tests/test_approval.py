"""Auto-approve gating: only REQUIRED fields count, against the document
type's own confidence_threshold (default 0.95)."""

import pytest

from app.schemas.document_type import DocumentTypeCreate, DocumentTypeUpdate
from app.services.pipeline import _min_score, _required_min_score

SCORES = {
    "invoice_number": 0.95,
    "total_amount": 0.97,
    "buyer_gstin": 0.4,
    "currency": 0.4,
    "line_items": [
        {"description": 0.95, "hsn_sac": 0.4, "line_total": 0.95},
    ],
}


class TestRequiredMinScore:
    def test_ignores_optional_low_fields(self):
        assert _required_min_score(SCORES, ["invoice_number", "total_amount"]) == 0.95

    def test_missing_required_field_never_approves(self):
        assert _required_min_score(SCORES, ["invoice_number", "po_number"]) is None

    def test_required_table_field_flattens_cells(self):
        assert _required_min_score(SCORES, ["line_items"]) == 0.4

    def test_no_required_falls_back_to_all_fields(self):
        assert _required_min_score(SCORES, []) == _min_score(SCORES) == 0.4

    def test_empty_scores_never_approves(self):
        assert _required_min_score({}, ["invoice_number"]) is None


class TestThresholdValidation:
    def test_create_defaults_to_095(self):
        d = DocumentTypeCreate(
            name="T",
            schema_definition={"type": "object", "properties": {}},
        )
        assert d.confidence_threshold == 0.95

    def test_create_rejects_out_of_range(self):
        with pytest.raises(Exception):
            DocumentTypeCreate(
                name="T",
                schema_definition={"type": "object", "properties": {}},
                confidence_threshold=1.5,
            )

    def test_update_accepts_threshold(self):
        d = DocumentTypeUpdate(confidence_threshold=0.8)
        assert d.confidence_threshold == 0.8
