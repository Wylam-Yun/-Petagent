from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.runtime.ambient_bubble import DEFAULT_BACKOFF_MS, guard_ambient_bubble_output
from app.runtime.concurrency import ProviderBusyError, ServerBusyError
from app.runtime.expressions import ACTIVITY_RECOMMENDATIONS

router = APIRouter(prefix="/api/pet")


class AmbientClientState(BaseModel):
    visible: bool = False
    foreground: bool = False
    screen_on: bool = False
    idle: bool = False
    busy: bool = True
    input_active: bool = False
    recording: bool = False
    waiting_llm: bool = False
    waiting_tts: bool = False
    playing_tts: bool = False


class AmbientRequest(BaseModel):
    local_date: str
    scene: str = "post_conversation_idle"
    idle_step: int = Field(default=0, ge=0)
    idle_elapsed_ms: int = Field(default=0, ge=0)
    client_state: AmbientClientState


class AmbientEventRequest(BaseModel):
    event_id: str


@router.get("/state")
def get_pet_state(request: Request):
    return request.app.state.state_store.get_state()


@router.post("/session/resume")
def post_session_resume(request: Request):
    request.app.state.tick_service.apply_if_due()
    return request.app.state.state_store.get_state()


@router.post("/event")
def post_pet_event(payload: Dict[str, Any], request: Request):
    return request.app.state.dispatcher.handle_event(payload).dict()


def _ambient_block_reason(request: Request, payload: AmbientRequest) -> str:
    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    if scheduler and scheduler.is_frontend_stale():
        return "frontend_stale"
    state = payload.client_state
    if not state.visible:
        return "page_hidden"
    if not state.foreground:
        return "not_foreground"
    if not state.screen_on:
        return "screen_off"
    if not state.idle or state.busy:
        return "busy"
    if state.input_active:
        return "input_active"
    if state.recording:
        return "recording"
    if state.waiting_llm:
        return "waiting_llm"
    if state.waiting_tts:
        return "waiting_tts"
    if state.playing_tts:
        return "playing_tts"
    delay = DEFAULT_BACKOFF_MS[min(payload.idle_step, len(DEFAULT_BACKOFF_MS) - 1)]
    if payload.idle_elapsed_ms < delay:
        return "too_early"
    return ""


@router.post("/ambient/check")
def post_ambient_check(payload: AmbientRequest, request: Request):
    block = _ambient_block_reason(request, payload)
    svc = request.app.state.ambient_bubble_service
    server = svc.can_emit(payload.local_date)
    if block:
        return {"eligible": False, "block_reason": block}
    if not server["eligible"]:
        return server
    return {
        "eligible": True,
        "block_reason": "",
        "next_activity": svc.select_activity(payload.local_date),
    }


def _generate_ambient_payload(payload: AmbientRequest, request: Request, activity: str) -> dict:
    pet_state = request.app.state.state_store.get_state()
    recent_dialogue = request.app.state.event_log_store.recent_dialogue_turns(limit=5)
    gate = request.app.state.provider_gate
    gate.acquire("llm_fast")
    try:
        ambient_brain = getattr(request.app.state, "fast_brain", None) or request.app.state.dispatcher.brain
        return ambient_brain.generate_ambient_bubble(
            scene=payload.scene,
            idle_step=payload.idle_step,
            idle_minutes=int(payload.idle_elapsed_ms / 60000),
            suggested_activity=activity,
            pet_state=pet_state,
            recent_dialogue=recent_dialogue,
        )
    finally:
        gate.release("llm_fast")


@router.post("/ambient/trigger")
async def post_ambient_trigger(payload: AmbientRequest, request: Request):
    block = _ambient_block_reason(request, payload)
    svc = request.app.state.ambient_bubble_service
    if block:
        return {"active": False, "block_reason": block}
    can_emit = svc.begin_generation(payload.local_date)
    if not can_emit["eligible"]:
        return {"active": False, "block_reason": can_emit["block_reason"]}
    try:
        activity = svc.select_activity(payload.local_date)
        if not activity:
            svc.record_failure("no_available_activity")
            return {"active": False, "block_reason": "no_available_activity"}
        rec = ACTIVITY_RECOMMENDATIONS[activity]
        executor = request.app.state.agent_work_executor
        raw = await executor.submit(
            partial(_generate_ambient_payload, payload, request, activity),
            timeout_s=45,
        )
        action = guard_ambient_bubble_output(raw, rec)
        if action is None:
            svc.record_failure("validation_failed")
            return {"active": False, "block_reason": "validation_failed"}

        event_id = "ambient-%s-%s" % (
            datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
            uuid4().hex[:8],
        )
        created = svc.create_pending(
            local_date=payload.local_date,
            event_id=event_id,
            activity=activity,
            activity_class=rec.activity_class,
            bubble=action.bubble,
            expression_key=action.expression_key,
            action=action.action,
        )
        if not created:
            return {"active": False, "block_reason": "pending_or_limit_changed"}
        return {
            "active": True,
            "event_id": event_id,
            "bubble": action.bubble,
            "expression_key": action.expression_key,
            "action": action.action,
            "audio_job_id": None,
            "voice_url": None,
            "runtime": {
                "source": action.source,
                "suggested_activity": activity,
                "activity_class": rec.activity_class,
            },
        }
    except ServerBusyError:
        svc.record_failure("server_busy")
        return {"active": False, "block_reason": "server_busy"}
    except ProviderBusyError:
        svc.record_failure("provider_busy")
        return {"active": False, "block_reason": "provider_busy"}
    except Exception:
        svc.record_failure("llm_provider_error")
        return {"active": False, "block_reason": "llm_provider_error"}
    finally:
        svc.end_generation()


@router.post("/ambient/confirm")
def post_ambient_confirm(payload: AmbientEventRequest, request: Request):
    ok = request.app.state.ambient_bubble_service.confirm_pending(payload.event_id)
    return {"ok": ok}


@router.post("/ambient/cancel")
def post_ambient_cancel(payload: AmbientEventRequest, request: Request):
    ok = request.app.state.ambient_bubble_service.cancel_pending(payload.event_id)
    return {"ok": ok}


@router.get("/proactive")
def get_pet_proactive(request: Request):
    return {"active": False, "legacy_disabled": True}


@router.post("/proactive/trigger")
def trigger_pet_proactive(request: Request, mode: str = ""):
    raise HTTPException(
        status_code=410,
        detail={
            "error": "Legacy proactive endpoint disabled; use /api/pet/ambient/*",
            "error_class": "legacy_proactive_disabled",
        },
    )
