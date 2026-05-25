from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/audio")


@router.get("/jobs/{job_id}")
def get_audio_job(job_id: str, request: Request):
    job = request.app.state.audio_job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audio job not found")
    return job.dict()


@router.post("/jobs/{job_id}/retry")
def retry_audio_job(job_id: str, request: Request):
    mgr = request.app.state.audio_job_manager
    old = mgr.get(job_id)
    if old is None:
        raise HTTPException(status_code=404, detail="Audio job not found")
    if old.status in ("pending", "ready", "superseded"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job in status '{old.status}'",
        )
    new_id = mgr.retry(job_id)
    if new_id is None:
        raise HTTPException(status_code=400, detail="Retry failed")
    return {"new_job_id": new_id}
