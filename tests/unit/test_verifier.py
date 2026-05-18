"""Verifier unit tests."""

from __future__ import annotations

import pytest

from tests.conftest import FakeLLM


@pytest.mark.unit
async def test_verifier_uses_extractions_as_primary_evidence():
    """Even with an empty snapshot, extractions should drive success=true."""
    from src.core.verifier import Verifier

    fake = FakeLLM(responses=[{
        "success": True,
        "confidence": 0.95,
        "reason": "EXTRACTED DATA contains the requested IP",
        "missing": [],
    }])
    verifier = Verifier(llm=fake)  # type: ignore[arg-type]

    verdict = await verifier.verify(
        goal="get my IP",
        success_criteria=["origin present"],
        final_summary="(agent did not declare done)",
        final_snapshot_text="(empty page)",
        extractions=['{"origin": "1.2.3.4"}'],
    )
    assert verdict["success"] is True
    assert verdict["confidence"] >= 0.9

    # Verify the LLM was given the extractions
    last_call = fake.calls[-1]
    assert "1.2.3.4" in last_call["user"]
