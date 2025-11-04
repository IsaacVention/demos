from __future__ import annotations
from typing import Optional, Sequence, List
from pydantic import BaseModel

from src.vention_communication import RpcBundle


# ---------- Pydantic models (for proto generation) ----------

class SMStateResponse(BaseModel):
    state: str
    last_state: str | None = None


class SMHistoryEntry(BaseModel):
    state: str
    trigger: str | None = None


class SMHistoryResponse(BaseModel):
    history: List[SMHistoryEntry]


class SMTriggerResponse(BaseModel):
    result: str
    previous_state: str
    new_state: str


# ---------- Bundle builder ----------

def build_state_machine_bundle(
    sm,
    *,
    include_state_actions: bool = True,
    include_history_action: bool = True,
    triggers: Optional[Sequence[str]] = None,
) -> "RpcBundle":
    """
    Build and return a unary-only RpcBundle exposing the given state machine.
    The returned bundle can be passed to app.extend_bundle(bundle).

    Streams are intentionally *not* included in this first version.
    """
    from src.vention_communication.entries import RpcBundle, ActionEntry

    bundle = RpcBundle()

    # (1) GetState
    if include_state_actions:
        async def get_state() -> SMStateResponse:
            return SMStateResponse(
                state=sm.state,
                last_state=getattr(sm, "get_last_state", lambda: None)(),
            )

        bundle.actions.append(ActionEntry(
            name="GetState",
            func=get_state,
            input_type=None,
            output_type=SMStateResponse,
        ))

    # (2) GetHistory
    if include_history_action:
        async def get_history() -> SMHistoryResponse:
            raw_hist = getattr(sm, "history", [])
            entries = []
            for item in raw_hist:
                if isinstance(item, dict):
                    entries.append(SMHistoryEntry(
                        state=str(item.get("state", "")),
                        trigger=item.get("trigger"),
                    ))
                else:
                    entries.append(SMHistoryEntry(state=str(item)))
            return SMHistoryResponse(history=entries)

        bundle.actions.append(ActionEntry(
            name="GetHistory",
            func=get_history,
            input_type=None,
            output_type=SMHistoryResponse,
        ))

    # (3) Triggers
    all_triggers = sorted(sm.events.keys())
    wanted = all_triggers if triggers is None else list(triggers)

    for trig in wanted:
        async def trigger_call(name=trig) -> SMTriggerResponse:
            current = sm.state
            available = sm.get_triggers(current)
            if name not in available:
                raise RuntimeError(
                    f"Trigger '{name}' not allowed from '{current}'. "
                    f"Available: {sorted(available)}"
                )
            method = getattr(sm, name)
            res = method()
            if hasattr(res, "__await__"):
                await res
            return SMTriggerResponse(
                result=name,
                previous_state=current,
                new_state=sm.state,
            )

        bundle.actions.append(ActionEntry(
            name=trig,
            func=trigger_call,
            input_type=None,
            output_type=SMTriggerResponse,
        ))

    return bundle
