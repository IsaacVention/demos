from __future__ import annotations

import inspect
from datetime import datetime
from typing import Optional, OrderedDict, Sequence
from enum import Enum

from src.vention_communication.entries import RpcBundle, ActionEntry
from src.vention_communication.errors import ConnectError
from vention_state_machine.src.state_machine.core import StateMachine
from vention_state_machine.src.state_machine.utils import (
    StateResponse,
    HistoryResponse,
    HistoryEntry,
    TriggerResponse,
)
from vention_state_machine.src.state_machine.defs import StateGroup


__all__ = ["build_state_machine_bundle"]


def _build_state_enum(sm: StateMachine):
    states = list(sm.get_nested_state_names())
    return Enum("StateMachineStates", {s: s for s in states})

def _build_trigger_enum(state_machine: StateMachine):
    triggers = list(state_machine.events.keys())
    return Enum("StateMachineTriggers", {t: t for t in triggers})

def build_state_machine_bundle(
    sm: StateMachine,
    *,
    include_state_actions: bool = True,
    include_history_action: bool = True,
    triggers: Optional[Sequence[str]] = None,
) -> RpcBundle:
    """
    Build and return an RpcBundle exposing a StateMachine instance.

    Provides unary RPCs:

      - GetState
      - GetHistory
      - Trigger_<TriggerName> (one per trigger)

    For integration via app.extend_bundle(bundle).
    """
    bundle = RpcBundle()

    # ======================================================
    # GetState
    # ======================================================
    if include_state_actions:

        async def get_state() -> StateResponse:
            last = getattr(sm, "get_last_state", lambda: None)()
            return StateResponse(state=sm.state, last_state=last)

        bundle.actions.append(
            ActionEntry(
                name="GetState",
                func=get_state,
                input_type=None,
                output_type=StateResponse,
            )
        )

    # ======================================================
    # GetHistory
    # ======================================================
    if include_history_action:

        async def get_history() -> HistoryResponse:
            raw = getattr(sm, "history", [])
            out = []

            for item in raw:
                if isinstance(item, dict):
                    # Handle dict items from history
                    entry_data = {
                        "state": str(item.get("state", "")),
                        "duration_ms": item.get("duration_ms"),
                    }
                    # Add timestamp if present, otherwise use current time
                    if "timestamp" in item:
                        entry_data["timestamp"] = item["timestamp"]
                    else:
                        entry_data["timestamp"] = datetime.now()
                    out.append(HistoryEntry(**entry_data))
                else:
                    # Handle simple state strings
                    out.append(HistoryEntry(
                        state=str(item),
                        timestamp=datetime.now()
                    ))

            return HistoryResponse(
                history=out,
                buffer_size=len(raw)
            )

        bundle.actions.append(
            ActionEntry(
                name="GetHistory",
                func=get_history,
                input_type=None,
                output_type=HistoryResponse,
            )
        )

    # ======================================================
    # Triggers
    # ======================================================
    # Source of truth: transitions registered on SM
    all_triggers = sorted(sm.events.keys())
    selected = all_triggers if triggers is None else list(triggers)

    # ---------- factory function (fixes closure bug) ----------
    def make_trigger_handler(trigger_name: str):
        async def trigger_call() -> TriggerResponse:
            current = sm.state
            allowed = sm.get_triggers(current)

            # Precondition error if invalid in current state
            if trigger_name not in allowed:
                raise ConnectError(
                    code="failed_precondition",
                    message=(
                        f"Trigger '{trigger_name}' cannot run from '{current}'. "
                        f"Allowed: {sorted(allowed)}"
                    ),
                )

            # Fetch bound trigger method
            try:
                method = getattr(sm, trigger_name)
            except AttributeError as e:
                raise ConnectError(
                    code="internal",
                    message=f"StateMachine missing trigger '{trigger_name}'",
                ) from e

            # Execute trigger (sync or async)
            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                raise ConnectError(
                    code="internal",
                    message=f"Trigger '{trigger_name}' failed: {e}",
                ) from e

            return TriggerResponse(
                result=trigger_name,
                previous_state=current,
                new_state=sm.state,
            )

        return trigger_call

    # ---------- register each trigger ----------
    for trig in selected:
        rpc_name = f"Trigger_{trig[0].upper()}{trig[1:]}"  # PascalCase RPC names
        handler = make_trigger_handler(trig)

        bundle.actions.append(
            ActionEntry(
                name=rpc_name,
                func=handler,
                input_type=None,
                output_type=TriggerResponse,
            )
        )
        
    StatesEnum = _build_state_enum(sm)
    TriggersEnum = _build_trigger_enum(sm)

    bundle.models.append(StatesEnum)
    bundle.models.append(TriggersEnum)

    return bundle
