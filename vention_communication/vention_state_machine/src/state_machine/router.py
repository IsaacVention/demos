import asyncio
from datetime import datetime
from typing import Optional, Sequence, Union, cast
from fastapi import APIRouter, HTTPException, Response, status
from typing_extensions import TypedDict, NotRequired
from vention_state_machine.src.state_machine.core import StateMachine
from vention_state_machine.src.state_machine.defs import Trigger


# ----------- TypedDict response models -----------


class StateResponse(TypedDict):
    state: str
    last_state: Optional[str]


class HistoryEntry(TypedDict):
    timestamp: datetime
    state: str
    duration_ms: NotRequired[int]


class HistoryResponse(TypedDict):
    history: list[HistoryEntry]
    buffer_size: int


class TriggerResponse(TypedDict):
    result: str
    previous_state: str
    new_state: str


# ----------- Router setup -----------


def build_router(
    state_machine: StateMachine,
    triggers: Optional[Sequence[Union[str, Trigger]]] = None,
) -> APIRouter:
    """
    Create an APIRouter for a given state_machine instance.

    Routes:
    - GET /state → current state and last known state
    - GET /history → transition history
    - POST /<trigger> → trigger transition (e.g., /start)
    """
    router = APIRouter()

    _register_basic_routes(router, state_machine)
    resolved_triggers = _resolve_triggers(state_machine, triggers)
    for trigger in resolved_triggers:
        _add_trigger_route(router, state_machine, trigger)

    return router


# ----------- Basic routes -----------


def _register_basic_routes(router: APIRouter, state_machine: StateMachine) -> None:
    @router.get("/state", response_model=StateResponse)
    def get_state() -> StateResponse:
        """Return current and last known state."""
        return {
            "state": state_machine.state,
            "last_state": state_machine.get_last_state(),
        }

    @router.get("/history", response_model=HistoryResponse)
    def get_history(last_n_entries: Optional[int] = None) -> HistoryResponse:
        """
        Return transition history. If `last_n_entries` is provided and non-negative,
        returns only the most recent N entries. Otherwise returns the full buffer.
        """
        if last_n_entries is not None and last_n_entries < 0:
            data = []
        else:
            data = (
                state_machine.get_last_history_entries(last_n_entries)
                if last_n_entries is not None
                else state_machine.history
            )
        return {
            "history": cast(list[HistoryEntry], data),
            "buffer_size": len(state_machine.history),
        }

    @router.get("/diagram.svg", response_class=Response)
    def get_svg() -> Response:
        try:
            graph = state_machine.get_graph()
            svg_bytes = graph.pipe(format="svg")
            return Response(content=svg_bytes, media_type="image/svg+xml")
        except Exception as e:
            msg = str(e).lower()
            if "executable" in msg or "dot not found" in msg or "graphviz" in msg:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Graphviz is required to render the diagram. "
                        "Install the system package via brew or apt) "
                    ),
                )
            raise


# ----------- Trigger resolution -----------


def _resolve_triggers(
    state_machine: StateMachine,
    triggers: Optional[Sequence[Union[str, Trigger]]],
) -> list[str]:
    """Resolve and validate trigger names."""
    if triggers is None:
        return sorted(state_machine.events.keys())

    resolved = []
    for trigger in triggers:
        trigger_name = trigger.name if isinstance(trigger, Trigger) else trigger
        if trigger_name not in state_machine.events:
            raise ValueError(f"Unknown trigger: '{trigger_name}'")
        resolved.append(trigger_name)

    return resolved


# ----------- Trigger route generation -----------


def _add_trigger_route(
    router: APIRouter,
    state_machine: StateMachine,
    trigger: str,
) -> None:
    """Add a single trigger route to the router."""

    async def trigger_handler() -> TriggerResponse:
        previous_state = state_machine.state

        available_triggers = state_machine.get_triggers(previous_state)
        if trigger not in available_triggers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Trigger '{trigger}' not allowed from state '{previous_state}'. "
                f"Available triggers: {sorted(available_triggers)}",
            )

        try:
            method = getattr(state_machine, trigger)
            result = method()
            if asyncio.iscoroutine(result):
                await result

            return {
                "result": trigger,
                "previous_state": previous_state,
                "new_state": state_machine.state,
            }

        except AttributeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Trigger method '{trigger}' not found on state machine",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error executing trigger '{trigger}': {str(e)}",
            )

    router.add_api_route(
        path=f"/{trigger}",
        endpoint=trigger_handler,
        methods=["POST"],
        name=f"{trigger}_trigger",
        response_model=TriggerResponse,
    )
