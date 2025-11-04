from __future__ import annotations
from typing import Any, Dict, List, Union


class State:
    """
    Descriptor for a single leaf state in a hierarchical state machine.

    On class definition it captures its fully-qualified name, as well as
    the owning group and member names separately.
    """

    __slots__ = ("name", "group_name", "member_name")

    def __init__(self) -> None:
        self.name: str = ""
        self.group_name: str = ""
        self.member_name: str = ""

    def __set_name__(self, owner: type, attr_name: str) -> None:
        self.group_name = owner.__name__
        self.member_name = attr_name
        self.name = f"{self.group_name}_{self.member_name}"

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"


class StateGroup:
    """
    Base class for grouping related State descriptors.

    Subclass this, declare State fields, and `to_state_list()`
    will emit exactly the structure transitions needs.
    """

    def to_state_list(self) -> List[Dict[str, Any]]:
        """
        Build a single‐element list of a dict:

          {
            "name": "<GroupName>",
            "children": [{"name":"member"}...],
            "initial": "<member>"
          }

        transitions will register:
          <GroupName>_<member>
        as the leaf states.
        """
        children: List[Dict[str, str]] = []
        for _, descriptor in vars(self.__class__).items():
            if isinstance(descriptor, State):
                children.append({"name": descriptor.member_name})

        if not children:
            raise ValueError(f"{self.__class__.__name__} has no State members")

        initial = children[0]["name"]
        return [
            {
                "name": self.__class__.__name__,
                "children": children,
                "initial": initial,
            }
        ]


class Trigger:
    """
    Represents a state machine trigger/event.

    You give it exactly one name; `.transition(...)` then builds
    the dict transitions wants.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"

    def __call__(self) -> str:
        return self.name

    def transition(
        self, source: Union[str, State], dest: Union[str, State]
    ) -> Dict[str, str]:
        """
        Build {"trigger": self.name, "source": <src>, "dest": <dst>}.
        `source` / `dest` may be raw strings or StateKey instances.
        """
        src = source if isinstance(source, str) else str(source)
        dst = dest if isinstance(dest, str) else str(dest)
        return {"trigger": self.name, "source": src, "dest": dst}
