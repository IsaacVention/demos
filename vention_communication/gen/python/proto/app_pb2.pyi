from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SMStateResponse(_message.Message):
    __slots__ = ()
    STATE_FIELD_NUMBER: _ClassVar[int]
    LAST_STATE_FIELD_NUMBER: _ClassVar[int]
    state: str
    last_state: str
    def __init__(self, state: _Optional[str] = ..., last_state: _Optional[str] = ...) -> None: ...

class SMHistoryEntry(_message.Message):
    __slots__ = ()
    STATE_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_FIELD_NUMBER: _ClassVar[int]
    state: str
    trigger: str
    def __init__(self, state: _Optional[str] = ..., trigger: _Optional[str] = ...) -> None: ...

class SMHistoryResponse(_message.Message):
    __slots__ = ()
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    history: _containers.RepeatedCompositeFieldContainer[SMHistoryEntry]
    def __init__(self, history: _Optional[_Iterable[_Union[SMHistoryEntry, _Mapping]]] = ...) -> None: ...

class SMTriggerResponse(_message.Message):
    __slots__ = ()
    RESULT_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_STATE_FIELD_NUMBER: _ClassVar[int]
    NEW_STATE_FIELD_NUMBER: _ClassVar[int]
    result: str
    previous_state: str
    new_state: str
    def __init__(self, result: _Optional[str] = ..., previous_state: _Optional[str] = ..., new_state: _Optional[str] = ...) -> None: ...

class StateChangeEvent(_message.Message):
    __slots__ = ()
    OLD_STATE_FIELD_NUMBER: _ClassVar[int]
    NEW_STATE_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_FIELD_NUMBER: _ClassVar[int]
    TIME_REMAINING_FIELD_NUMBER: _ClassVar[int]
    old_state: str
    new_state: str
    trigger: str
    time_remaining: int
    def __init__(self, old_state: _Optional[str] = ..., new_state: _Optional[str] = ..., trigger: _Optional[str] = ..., time_remaining: _Optional[int] = ...) -> None: ...
