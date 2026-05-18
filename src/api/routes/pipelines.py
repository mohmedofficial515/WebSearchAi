"""Pipeline lifecycle endpoints.

The chat route plans pipelines and stores them in an in-memory registry
(`src/api/routes/chat.py::_PIPELINES`). These endpoints expose the
approve/cancel/resume controls the React PipelineCard renders.

  POST /api/pipelines/{id}/approve  — start a paused-for-approval pipeline
  POST /api/pipelines/{id}/cancel   — drop a planned-but-unstarted pipeline
  POST /api/pipelines/{id}/resume   — resume after pipeline_paused, with user inputs
  GET  /api/pipelines/{id}          — read current pipeline state
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import chat as chat_module


router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


class ResumeBody(BaseModel):
    step_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str) -> dict:
    p = chat_module.get_pipeline(pipeline_id)
    if p is None:
        raise HTTPException(404, detail="الخطة غير موجودة أو منتهية الصلاحية")
    return p.to_dict()


@router.post("/{pipeline_id}/approve")
async def approve_pipeline(pipeline_id: str) -> dict:
    p = chat_module.get_pipeline(pipeline_id)
    if p is None:
        raise HTTPException(404, detail="الخطة غير موجودة أو منتهية الصلاحية")
    await chat_module._start_pipeline_run(p)
    return {"ok": True, "pipeline_id": pipeline_id, "status": "running"}


@router.post("/{pipeline_id}/cancel")
async def cancel_pipeline(pipeline_id: str) -> dict:
    p = chat_module.get_pipeline(pipeline_id)
    if p is None:
        raise HTTPException(404, detail="الخطة غير موجودة أو منتهية الصلاحية")
    chat_module.forget_pipeline(pipeline_id)
    return {"ok": True, "pipeline_id": pipeline_id, "status": "cancelled"}


@router.post("/{pipeline_id}/resume")
async def resume_pipeline(pipeline_id: str, body: ResumeBody) -> dict:
    """Resume a paused pipeline after the user has filled in $askUser fields."""
    p = chat_module.get_pipeline(pipeline_id)
    if p is None:
        raise HTTPException(404, detail="الخطة غير موجودة أو منتهية الصلاحية")
    await chat_module._start_pipeline_run(p)  # noqa: SLF001 — friendly helper
    return {"ok": True, "pipeline_id": pipeline_id, "status": "resumed"}
