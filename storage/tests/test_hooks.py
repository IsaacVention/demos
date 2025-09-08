from __future__ import annotations

from sqlmodel import Session
from storage.hooks import HookRegistry
from storage_tests.fixtures import StorageTestCase, TestModel


class TestHooks(StorageTestCase):
    def test_hook_registry_initialization(self) -> None:
        """HookRegistry initializes with empty hook collections."""
        registry = HookRegistry[TestModel]()
        self.assertEqual(len(registry._hooks), 0)

    def test_decorator_registration(self) -> None:
        """Hook decorators properly register functions for events."""
        registry = HookRegistry[TestModel]()

        # Register hooks for different events
        @registry.decorator("before_insert")
        def before_insert_hook(session: Session, instance: TestModel) -> None:
            pass

        @registry.decorator("after_insert")
        def after_insert_hook(session: Session, instance: TestModel) -> None:
            pass

        @registry.decorator("before_update")
        def before_update_hook(session: Session, instance: TestModel) -> None:
            pass

        # Verify hooks are registered
        self.assertEqual(len(registry._hooks["before_insert"]), 1)
        self.assertEqual(len(registry._hooks["after_insert"]), 1)
        self.assertEqual(len(registry._hooks["before_update"]), 1)
        self.assertEqual(len(registry._hooks["before_delete"]), 0)  # Not registered

    def test_emit_executes_registered_hooks(self) -> None:
        """emit() executes all hooks registered for an event."""
        registry = HookRegistry[TestModel]()
        executed_hooks = []

        @registry.decorator("before_insert")
        def hook1(session: Session, instance: TestModel) -> None:
            executed_hooks.append("hook1")

        @registry.decorator("before_insert")
        def hook2(session: Session, instance: TestModel) -> None:
            executed_hooks.append("hook2")

        @registry.decorator("after_insert")
        def hook3(session: Session, instance: TestModel) -> None:
            executed_hooks.append("hook3")

        # Execute hooks
        with Session(self.engine) as session:
            instance = TestModel(name="test")
            registry.emit("before_insert", session=session, instance=instance)
            registry.emit("after_insert", session=session, instance=instance)

        # Verify execution order
        self.assertEqual(executed_hooks, ["hook1", "hook2", "hook3"])

    def test_emit_with_no_hooks(self) -> None:
        """emit() handles events with no registered hooks gracefully."""
        registry = HookRegistry[TestModel]()

        with Session(self.engine) as session:
            instance = TestModel(name="test")
            registry.emit("before_delete", session=session, instance=instance)

    def test_hook_execution_order(self) -> None:
        """Hooks execute in the order they were registered."""
        registry = HookRegistry[TestModel]()
        execution_order = []

        @registry.decorator("before_insert")
        def first_hook(session: Session, instance: TestModel) -> None:
            execution_order.append(1)

        @registry.decorator("before_insert")
        def second_hook(session: Session, instance: TestModel) -> None:
            execution_order.append(2)

        @registry.decorator("before_insert")
        def third_hook(session: Session, instance: TestModel) -> None:
            execution_order.append(3)

        with Session(self.engine) as session:
            instance = TestModel(name="test")
            registry.emit("before_insert", session=session, instance=instance)

        self.assertEqual(execution_order, [1, 2, 3])

    def test_hook_function_identity(self) -> None:
        """Decorator returns the original function unchanged."""
        registry = HookRegistry[TestModel]()

        def original_hook(session: Session, instance: TestModel) -> None:
            pass

        decorated_hook = registry.decorator("before_insert")(original_hook)

        # Should be the same function object
        self.assertIs(decorated_hook, original_hook)

    def test_multiple_hooks_same_event(self) -> None:
        """Multiple hooks can be registered for the same event."""
        registry = HookRegistry[TestModel]()
        hook_count = 0

        for _ in range(5):

            @registry.decorator("before_insert")
            def hook(session: Session, instance: TestModel) -> None:
                nonlocal hook_count
                hook_count += 1

        with Session(self.engine) as session:
            instance = TestModel(name="test")
            registry.emit("before_insert", session=session, instance=instance)

        self.assertEqual(hook_count, 5)
