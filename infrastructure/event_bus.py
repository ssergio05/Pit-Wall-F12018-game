import threading
from typing import Callable, Dict, List, Any

class EventBus:
    """
    Thread-safe Publisher/Subscriber event bus.
    Routes telemetry packets from adapters to the UI and Strategy Engine
    without tightly coupling the components.
    """
    
    def __init__(self):
        # Dictionary mapping event types to a list of callback functions
        self._subscribers: Dict[str, List[Callable]] = {}
        # Mutex lock to prevent race conditions when multiple threads publish at 60Hz
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Registers a callback function to listen for a specific event type.
        
        Args:
            event_type (str): The name of the channel (e.g., "TELEMETRY_UPDATE").
            callback (Callable): The function to execute when data arrives.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: Any) -> None:
        """
        Dispatches data to all callbacks subscribed to the event_type.
        
        Args:
            event_type (str): The name of the channel.
            data (Any): The payload (usually a TelemetryPacket object).
        """
        with self._lock:
            if event_type not in self._subscribers:
                return
            # Create a shallow copy of the list to avoid mutation issues during iteration
            callbacks = self._subscribers[event_type][:] 
        
        # Execute all subscribed callbacks
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"[EventBus] Error in subscriber callback for '{event_type}': {e}")

# Global singleton instance to be imported across the app
global_event_bus = EventBus()