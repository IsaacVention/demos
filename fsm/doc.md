# vention-state-machine

A lightweight wrapper around `transitions` for building async-safe, recoverable hierarchical state machines with minimal boilerplate.

## ✨ Features

- Built-in `ready` / `fault` states
- Global transitions: `to_fault`, `reset`
- Optional state recovery (`recover__state`)
- Async task spawning and cancellation
- Timeouts and auto-fault handling
- Transition history recording with timestamps + durations

## 🧠 Domain-Specific Language

This library uses a **declarative domain-specific language (DSL)** to define state machines in a readable and structured way. The key building blocks are:

- **`State`**: Represents a single leaf node in the state machine. Declared as a class attribute.
    
- **`StateGroup`**: A container for related states. It generates a hierarchical namespace for its child states (e.g. `MyGroup.my_state` becomes `"MyGroup_my_state"`).
    
- **`Trigger`**: Defines a named event that can cause state transitions. It is both callable (returns its name as a string) and composable (can generate transition dictionaries via `.transition(...)`).
    
This structure allows you to define states and transitions with strong typing and full IDE support — without strings scattered across your codebase.

For Example: 
```python
class MyStates(StateGroup):
    idle: State = State()
    working: State = State()

class Triggers:
    begin = Trigger("begin")
    finish = Trigger("finish")
```
You can then define transitions declaratively:
```python
TRANSITIONS = [
    Triggers.finish.transition(MyStates.working, MyStates.idle),
]
```

## 🧱 Base States and Triggers

Every machine comes with built-in:

- **States**:
  - `ready`: initial state
  - `fault`: global error state
- **Triggers**:
  - `start`: transition into the first defined state
  - `to_fault`: jump to fault from any state
  - `reset`: recover from fault back to ready

You can reference these via:

```python
from state_machine.core import BaseStates, BaseTriggers

state_machine.trigger(BaseTriggers.RESET.value)
assert state_machine.state == BaseStates.READY.value
```

## 🚀 Quick Start
### 1. Define Your States and Triggers

```python
from state_machine.defs import StateGroup, State, Trigger

class Running(StateGroup):
	picking: State = State()
	placing: State = State()
	homing: State = State()

class States:
	running = Running()

class Triggers:
	start = Trigger("start")
	finished_picking = Trigger("finished_picking")
	finished_placing = Trigger("finished_placing")
	finished_homing = Trigger("finished_homing")
	to_fault = Trigger("to_fault")
	reset = Trigger("reset")
```

### 2. Define Transitions
```python
TRANSITIONS  = [
	Triggers.start.transition("ready", States.running.picking),
	Triggers.finished_picking.transition(States.running.picking, States.running.placing),
	Triggers.finished_placing.transition(States.running.placing, States.running.homing),
	Triggers.finished_homing.transition(States.running.homing, States.running.picking)
]
```

### 3. Implement Your State Machine

```python
from state_machine.core import StateMachine

from state_machine.decorators import on_enter_state, auto_timeout

class CustomMachine(StateMachine):

def __init__(self):
	super().__init__(states=States, transitions=TRANSITIONS)

	# Automatically trigger to_fault after 5s if no progress
	@on_enter_state(States.running.picking)
	@auto_timeout(5.0, Triggers.to_fault)
	def enter_picking(self, _):
		print("🔹 Entering picking")

	@on_enter_state(States.running.placing)
	def enter_placing(self, _):
		print("🔸 Entering placing")
		
	@on_enter_state(States.running.homing)
	def enter_homing(self, _):
		print("🔺 Entering homing")
```

### 4. Start It
```python
state_machine = StateMachine()
state_machine.start() # Enters last recorded state (if recovery enabled), else first state
```

## 🌐 Optional FastAPI Router
This library provides a FastAPI-compatible router that automatically exposes your state machine over HTTP. This is useful for:

- Triggering transitions via HTTP POST
- Inspecting current state and state history
- Visualizing the state diagram as an SVG
 #### Example
 ```python
from fastapi import FastAPI
from state_machine.router import build_router
from state_machine.core import StateMachine

state_machine = StateMachine(...)
state_machine.start()

app = FastAPI()
app.include_router(build_router(state_machine))
```

### Available Routes
* `GET /state`: Returns current and last known state
* `GET /history`: Returns list of recent state transitions
* `GET /diagram.svg`: Returns an SVG rendering of the state machine
* `POST /<trigger_name>`: Triggers a transition by name

You can expose only a subset of triggers by passing them explicitly:
```python
from state_machine.defs import Trigger
# Only create endpoints for 'start' and 'reset'
router = build_router(state_machine, triggers=[Trigger("start"), Trigger("reset")])
```



## 🧪 Testing & History
-  `state_machine.history`: List of all transitions with timestamps and durations
-  `state_machine.last(n)`: Last `n` transitions
-  `state_machine.record_last_state()`: Manually record current state for later recovery
-  `state_machine.get_last_state()`: Retrieve recorded state
  
## ⏲ Timeout Example
Any `on_enter_state` method can be wrapped with `@auto_timeout(seconds, trigger_fn)`, e.g.:

```python
@auto_timeout(5.0, Triggers.to_fault)
```
This automatically triggers `to_fault()` if the state remains active after 5 seconds.

## 🔁 Recovery Example
Enable `enable_last_state_recovery=True` and use:
```python
state_machine.start()
```
If a last state was recorded, it will trigger `recover__{last_state}` instead of `start`.

## 🧩 How Decorators Work

Decorators attach metadata to your methods:

- `@on_enter_state(state)` binds to the state's entry callback
- `@on_exit_state(state)` binds to the state's exit callback
- `@auto_timeout(seconds, trigger)` schedules a timeout once the state is entered

The library automatically discovers and wires these up when your machine is initialized.