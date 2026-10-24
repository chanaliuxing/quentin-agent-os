from __future__ import annotations
import logging
from typing import Dict, Any, List, Callable, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

import asyncio
from collections import defaultdict

class EnvironmentEventBus:
    """
    P5: Ported from OpenClaw's SystemEvents bus.
    Enhanced with physical debouncing to prevent perception storms.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EnvironmentEventBus, cls).__new__(cls)
            cls._instance.subscribers: Dict[str, List[Callable]] = defaultdict(list)
            cls._instance._pending_payloads: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            cls._instance._debounce_tasks: Dict[str, asyncio.Task] = {}
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable):
        self.subscribers[event_type].append(callback)

    def emit(self, event_type: str, payload: Dict[str, Any], debounce_ms: int = 500):
        """
        Broadcasts with physical debouncing (OpenClaw Parity).
        """
        self._pending_payloads[event_type].append(payload)
        
        # If a debounce task is already running, cancel it to reset the timer
        if event_type in self._debounce_tasks:
            self._debounce_tasks[event_type].cancel()
            
        # Schedule new broadcast
        self._debounce_tasks[event_type] = asyncio.create_task(
            self._do_debounced_emit(event_type, debounce_ms)
        )

    async def _do_debounced_emit(self, event_type: str, delay_ms: int):
        try:
            await asyncio.sleep(delay_ms / 1000.0)
            
            # Atomic Collect and Merge
            payloads = self._pending_payloads.pop(event_type, [])
            if not payloads: return
            
            # Merge logic: if it's 'file_modified', we want a unique set of paths
            merged_payload = {"count": len(payloads)}
            if event_type == "file_modified":
                merged_payload["paths"] = list({p.get("path") for p in payloads if p.get("path")})
            else:
                merged_payload["items"] = payloads
                
            logger.info(f"EventBus: Broadcasing DEBOUNCED {event_type} ({len(payloads)} events merged)")

            # Unified BrainEvent emission (single protocol multi-channel).
            try:
                from quentin.runtime.system_events import system_events

                system_events.emit_brain_event(
                    session_id="global",
                    event_type=f"channel.{str(event_type or '').strip().lower() or 'event'}",
                    category="channel",
                    phase="update",
                    source="environment_bus",
                    payload={"event_type": event_type, "merged_payload": merged_payload},
                    turn_id="",
                )
            except Exception:
                pass
            
            for callback in self.subscribers[event_type]:
                try:
                    # Check if callback is async
                    if asyncio.iscoroutinefunction(callback):
                        await callback(merged_payload)
                    else:
                        callback(merged_payload)
                except Exception as e:
                    logger.error(f"EventBus: Callback error: {e}")
                    
        except asyncio.CancelledError:
            pass # Timer reset
        finally:
            self._debounce_tasks.pop(event_type, None)

# Global Singleton
environment_bus = EnvironmentEventBus()
