from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/audio")


@router.get("/jobs/{job_id}")
def get_audio_job(job_id: str, request: Request):
    job = request.app.state.audio_job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")
    return job.dict()
