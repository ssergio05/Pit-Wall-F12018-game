from core.models import TelemetryPacket
from infrastructure.event_bus import global_event_bus

class StrategyEngine:
    """
    The Decision Support System (DSS).
    Subscribes to telemetry updates, calculates physical degradation (fuel, tyres),
    and publishes strategic alerts back to the Event Bus.
    """

    def __init__(self):
        """Initialise the DSS with an empty driver-state registry and subscribe to telemetry."""
        self.driver_states = {}

        global_event_bus.subscribe("TELEMETRY_UPDATE", self._process_telemetry)
        print("[StrategyEngine] 🧠 DSS initialized and listening to telemetry stream.")

    def _process_telemetry(self, packet: TelemetryPacket) -> None:
        """Analyzes incoming telemetry and updates physical degradation models."""
        
        # Initialize default car setup if we see a driver for the first time
        if packet.driver_id not in self.driver_states:
            self.driver_states[packet.driver_id] = {
                "fuel_kg": 110.0,         # Starting race fuel
                "tyre_life_pct": 100.0,   # Fresh tyres
                "pit_alert_sent": False
            }
            
        state = self.driver_states[packet.driver_id]
        
        # --- 🧮 DETERMINISTIC PHYSICS ENGINE ---
        
        # 1. Fuel Consumption Logic (Time-warped x500 for testing)
        fuel_burn_rate = ((packet.throttle_pct / 100.0) * 0.002)
        state["fuel_kg"] -= fuel_burn_rate
        
        # 2. Tyre Degradation Logic (Time-warped x500 for testing)
        wear_factor = ((packet.speed_kmh / 350.0) * 0.001)
        state["tyre_life_pct"] -= wear_factor
        
        # Clamp values to prevent negative numbers
        state["fuel_kg"] = max(0.0, state["fuel_kg"])
        state["tyre_life_pct"] = max(0.0, state["tyre_life_pct"])
        
        # --- 🚨 STRATEGY EVALUATION ---
        self._evaluate_pit_window(packet.driver_id, state, packet.session_time)

    def _evaluate_pit_window(self, driver_id: str, state: dict, session_time: float) -> None:
        """Publish a pit-stop alert when tyre life drops below 30%."""
        if state["tyre_life_pct"] < 30.0 and not state["pit_alert_sent"]:

            alert_msg = (f"BOX BOX! {driver_id} tyre life critical "
                         f"({state['tyre_life_pct']:.1f}%).")
            
            global_event_bus.publish("STRATEGY_ALERT", {
                "driver": driver_id,
                "message": alert_msg,
                "timestamp": session_time
            })
            state["pit_alert_sent"] = True