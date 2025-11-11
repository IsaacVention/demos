from __future__ import annotations

import inspect
from typing import Optional, Sequence

from src.vention_communication.entries import RpcBundle, ActionEntry
from src.vention_communication.errors import ConnectError
from vention_state_machine.src.state_machine.core import StateMachine
from vention_state_machine.src.state_machine.router import (
    StateResponse,
    HistoryResponse,
    HistoryEntry,
    TriggerResponse,
)

__all__ = ["build_state_machine_bundle"]


def build_state_machine_bundle(
    sm: StateMachine,
    *,
    include_state_actions: bool = True,
    include_history_action: bool = True,
    triggers: Optional[Sequence[str]] = None,
) -> RpcBundle:
    """
    Build and return an RpcBundle exposing the given StateMachine instance.

    The resulting bundle provides unary RPCs roughly equivalent to the REST
    endpoints in `router.py`, including:

      - GetState        → Current + last known state
      - GetHistory      → Transition history (with duration_ms)
      - Trigger<name>   → One RPC per state-machine trigger

    Intended for integration via `app.extend_bundle(bundle)`.
    """
    bundle = RpcBundle()

    # --------------------- GetState ---------------------

    if include_state_actions:

        async def get_state() -> StateResponse:
            """Return the current and last known FSM state."""
            return StateResponse(
                state=sm.state,
                last_state=getattr(sm, "get_last_state", lambda: None)(),
            )

        bundle.actions.append(
            ActionEntry(
                name="GetState",
                func=get_state,
                input_type=None,
                output_type=StateResponse,
            )
        )

    # --------------------- GetHistory ---------------------

    if include_history_action:

        async def get_history() -> HistoryResponse:
            """Return transition history with optional duration_ms values."""
            raw_hist = getattr(sm, "history", [])
            entries: list[HistoryEntry] = []
            for item in raw_hist:
                # Flexible support for both dict-style and custom entries
                if isinstance(item, dict):
                    entries.append(
                        HistoryEntry(
                            state=str(item.get("state", "")),
                            trigger=item.get("trigger"),
                            duration_ms=item.get("duration_ms"),
                        )
                    )
                else:
                    # fallback: bare state name
                    entries.append(HistoryEntry(state=str(item)))
            return HistoryResponse(history=entries)

        bundle.actions.append(
            ActionEntry(
                name="GetHistory",
                func=get_history,
                input_type=None,
                output_type=HistoryResponse,
            )
        )

    # --------------------- Triggers ---------------------

    all_triggers = sorted(sm.events.keys())
    wanted = all_triggers if triggers is None else list(triggers)

    for trig in wanted:
        rpc_name = f"Trigger_{trig[0].upper()}{trig[1:]}"  # Prefix + PascalCase

        async def trigger_call(name: str = trig) -> TriggerResponse:
            """Invoke a state-machine trigger safely with RPC-compatible errors."""
            current = sm.state
            available = sm.get_triggers(current)

            if name not in available:
                # Equivalent to HTTP 409 in REST router
                raise ConnectError(
                    code="failed_precondition",
                    message=(
                        f"Trigger '{name}' not allowed from '{current}'. "
                        f"Available triggers: {sorted(available)}"
                    ),
                )

            try:
                method = getattr(sm, name)
            except AttributeError as e:
                raise ConnectError(
                    code="internal",
                    message=f"Trigger method '{name}' not found on state machine",
                ) from e

            try:
                result = method()
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                raise ConnectError(
                    code="internal",
                    message=f"Error executing trigger '{name}': {e}",
                ) from e

            return TriggerResponse(
                result=name,
                previous_state=current,
                new_state=sm.state,
            )

        bundle.actions.append(
            ActionEntry(
                name=rpc_name,
                func=trigger_call,
                input_type=None,
                output_type=TriggerResponse,
            )
        )

    return bundle
