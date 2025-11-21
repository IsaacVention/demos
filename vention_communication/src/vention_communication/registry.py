from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Set, Type, get_args, get_origin, Union

from pydantic import BaseModel

from .entries import RpcBundle
from .typing_utils import is_pydantic_model, apply_aliases


@dataclass
class RpcRegistry:
    """
    Central registry that collects RPC bundles, applies model normalization
    (Pydantic field aliasing), and exposes a unified bundle.

    - Plugins and decorators add RpcBundle instances.
    - Registry merges them.
    - Registry applies camelCase aliases to all Pydantic models exactly once.
    """

    service_name: str = "VentionApp"
    _bundles: List[RpcBundle] = field(default_factory=list)
    _models_normalized: bool = False

    # ------------- Bundle registration -------------

    def add_bundle(self, bundle: RpcBundle) -> None:
        """Register a bundle for inclusion in the unified RPC view."""
        self._bundles.append(bundle)

    @property
    def bundle(self) -> RpcBundle:
        """Return a merged RpcBundle (does not mutate stored bundles)."""
        merged = RpcBundle()
        for bundle in self._bundles:
            merged.extend(bundle)
        return merged

    # ------------- Model normalization / aliasing -------------

    def _unwrap_optional(self, field_type: Any) -> Any:
        """Unwrap Optional[Type] or Union[Type, None] to get the non-None type."""
        origin = get_origin(field_type)
        if origin is not Union:
            return field_type

        args = get_args(field_type)
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return non_none_args[0]
        return field_type

    def _unwrap_list(self, field_type: Any) -> Any:
        """Unwrap List[Type] to get the inner type, handling Optional inside List."""
        origin = get_origin(field_type)
        if origin not in (list, List):
            return field_type

        args = get_args(field_type)
        if not args:
            return field_type

        inner_type = args[0]
        return self._unwrap_optional(inner_type)

    def _extract_nested_models(self, field_type: Any) -> List[Type[BaseModel]]:
        """Extract Pydantic models from a field type, handling Optional, List, etc."""
        field_type = self._unwrap_optional(field_type)
        field_type = self._unwrap_list(field_type)

        if is_pydantic_model(field_type):
            return [field_type]
        return []

    def _normalize_model(self, model: Optional[Type[BaseModel]], seen: Set[Type[BaseModel]]) -> None:
        """Recursively normalize a model and all its nested models."""
        if model is None:
            return
        if not is_pydantic_model(model):
            return
        if model in seen:
            return

        seen.add(model)
        apply_aliases(model)

        if hasattr(model, "model_fields"):
            for _, field_info in model.model_fields.items():
                nested_models = self._extract_nested_models(field_info.annotation)
                for nested_model in nested_models:
                    self._normalize_model(nested_model, seen)

    def normalize_models_and_apply_aliases(self) -> None:
        """
        Walk all RPCs in all bundles and apply camelCase JSON aliases
        to every Pydantic model exactly once, including nested models.

        After this runs, nothing else in the system should call apply_aliases_to_model().
        """
        if self._models_normalized:
            return

        seen: Set[Type[BaseModel]] = set()

        for bundle in self._bundles:
            for action in bundle.actions:
                self._normalize_model(action.input_type, seen)
                self._normalize_model(action.output_type, seen)
            for stream in bundle.streams:
                self._normalize_model(stream.payload_type, seen)

        self._models_normalized = True

    # ------------- Unified, normalized view -------------

    def get_unified_bundle(self) -> RpcBundle:
        """
        Get the fully merged, normalized RPC bundle.

        This will apply aliasing exactly once and then return a merged RpcBundle.
        """
        self.normalize_models_and_apply_aliases()
        return self.bundle
