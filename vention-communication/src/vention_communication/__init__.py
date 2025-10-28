"""
Vention Communication — unified IPC layer for Machine Apps.

Exports the minimal public API: VentionApp, action, stream, RpcBundle.
"""

from .app import VentionApp
from .decorators import action, stream
from .entries import RpcBundle

__all__ = ["VentionApp", "action", "stream", "RpcBundle"]
