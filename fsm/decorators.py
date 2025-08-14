def on_enter_state(state_node):
    if hasattr(state_node, "name"):
        state_name = state_node.name
    elif isinstance(state_node, str):
        state_name = state_node
    else:
        raise TypeError(f"Expected a StateNode or str, got {type(state_node)}")

    def decorator(fn):
        fn._on_enter_state = state_name
        return fn

    return decorator

def on_exit_state(state_node: str):
    if hasattr(state_node, "name"):
        state_name = state_node.name
    elif isinstance(state_node, str):
        state_name = state_node
    else:
        raise TypeError(f"Expected a StateNode or str, got {type(state_node)}")

    def decorator(fn):
        fn._on_exit_state = state_name
        return fn

    return decorator


def auto_timeout(seconds: float, trigger: str = "to_fault"):
    def decorator(fn):
        fn._timeout_config = (seconds, trigger)
        return fn

    return decorator