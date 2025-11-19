from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Type, get_args, get_origin, Union

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

    def normalize_models_and_apply_aliases(self) -> None:
        """
        Walk all RPCs in all bundles and apply camelCase JSON aliases
        to every Pydantic model exactly once, including nested models.

        After this runs, nothing else in the system should call apply_aliases_to_model().
        """
        if self._models_normalized:
            return

        seen: Set[Type] = set()

        def _extract_nested_models(field_type: Type) -> List[Type]:
            """Extract Pydantic models from a field type, handling Optional, List, etc."""
            nested: List[Type] = []
            
            # Handle Optional[Type] -> Union[Type, None]
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                # Filter out None type
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    field_type = non_none_args[0]
                    origin = get_origin(field_type)
            
            # Handle List[Type]
            if origin in (list, List):
                args = get_args(field_type)
                if args:
                    field_type = args[0]
                    origin = get_origin(field_type)
                    # Handle Optional inside List
                    if origin is Union:
                        args = get_args(field_type)
                        non_none_args = [arg for arg in args if arg is not type(None)]
                        if len(non_none_args) == 1:
                            field_type = non_none_args[0]
            
            # Check if the final type is a Pydantic model
            if is_pydantic_model(field_type):
                nested.append(field_type)
            
            return nested

        def normalize_model(model: Optional[Type]) -> None:
            """Recursively normalize a model and all its nested models."""
            if model is None:
                return
            if not is_pydantic_model(model):
                return
            if model in seen:
                return
            seen.add(model)
            apply_aliases(model)
            
            # Recursively normalize nested models
            if hasattr(model, "model_fields"):
                for field_name, field_info in model.model_fields.items():
                    nested_models = _extract_nested_models(field_info.annotation)
                    for nested_model in nested_models:
                        normalize_model(nested_model)

        for bundle in self._bundles:
            for action in bundle.actions:
                normalize_model(action.input_type)
                normalize_model(action.output_type)
            for stream in bundle.streams:
                normalize_model(stream.payload_type)

        self._models_normalized = True

    # ------------- Unified, normalized view -------------

    def get_unified_bundle(self) -> RpcBundle:
        """
        Get the fully merged, normalized RPC bundle.

        This will apply aliasing exactly once and then return a merged RpcBundle.
        """
        self.normalize_models_and_apply_aliases()
        return self.bundle