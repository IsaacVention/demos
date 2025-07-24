import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import asyncio
from fsm import FoundationFSM

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def simple_fsm():
    states = ["foo"]
    transitions = [
        {"trigger": "start", "source": "ready", "dest": "foo"},
        {"trigger": "reset", "source": "foo",   "dest": "ready"},
    ]
    return FoundationFSM(states=states, transitions=transitions)