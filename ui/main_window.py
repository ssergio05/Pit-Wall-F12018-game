import customtkinter as ctk
import queue
from typing import Dict
import json
import os

# Import Core Schema and Event Bus
from core.models import TelemetryPacket
from infrastructure.event_bus import global_event_bus
from ui.components.telemetry_graph import LiveTelemetryGraph


class PitWallDashboard(ctk.CTk):
    """
    Main application window for Pit Wall OS.

    Manages the CTk UI lifecycle, subscribes to the event bus for telemetry
    updates, and drives a decoupled rendering loop that redraws the
    Matplotlib-based telemetry graph at a throttled rate (~10 FPS).

    Attributes:
        telemetry_graph (LiveTelemetryGraph): The embedded telemetry panel.
        driver_histories (dict): Per-driver ring buffers of recent telemetry.
        ref_data (dict): Best-lap reference data for ghost-line overlay.
        _latest_telemetry (dict): Most recent TelemetryPacket per driver ID.
        _new_telemetry (bool): Dirty flag set by the event-bus callback.
    """

    def __init__(self):
        super().__init__()
        
        self.title("Pit Wall OS - V2 Architecture")
        self.geometry("900x600")
        ctk.set_appearance_mode("dark")
        
        # --- Thread-Safe Buffers ---
        self._latest_telemetry: Dict[str, TelemetryPacket] = {}
        
        # Historical storage for all drivers (unbounded — cleared on lap reset)
        from collections import deque
        self.driver_histories: Dict[str, Dict[str, deque]] = {}
        self._last_lap_distance: Dict[str, float] = {}

        # Telemetry Ghost: best lap time and reference lap data per driver
        self.best_lap_time: Dict[str, float] = {}
        self.ref_data: Dict[str, Dict[str, list]] = {}

        # Dirty flag: the render loop only redraws matplotlib when new data arrives
        self._new_telemetry = False

        # Queue for strategy alerts (FIFO) so we don't miss any messages
        self._alerts_queue = queue.Queue()

        self.track_metadata = self._load_track_metadata()
        
        # --- UI Layout Setup ---
        self._setup_ui()
        
        # --- Event Bus Subscriptions ---
        global_event_bus.subscribe("TELEMETRY_UPDATE", self._on_telemetry_received)
        global_event_bus.subscribe("STRATEGY_ALERT", self._on_strategy_alert)
        
        # Start the decoupled UI rendering loop (runs at ~10 FPS max)
        self._render_loop()

    def _setup_ui(self):
        """Builds the visual skeleton of the dashboard."""
        # Top Header
        self.lbl_title = ctk.CTkLabel(self, text="🏎️ Live Race Telemetry", font=("Helvetica", 24, "bold"))
        self.lbl_title.pack(pady=(10, 0))
        
        # Inject the Graph
        self.telemetry_graph = LiveTelemetryGraph(self, driver_1="VER", height=750, track_metadata=self.track_metadata)
        self.telemetry_graph.pack(padx=40, fill="both", expand=True)
        
        # Strategy Alerts Console (below the graph)
        self.txt_console = ctk.CTkTextbox(self, height=100, state="disabled", fg_color="#1e1e1e", text_color="#00FF00")
        self.txt_console.pack(padx=40, fill="both", pady=(0, 20))

    # --- EVENT BUS CALLBACKS (Running on Background Threads) ---
    
    def _on_telemetry_received(self, packet: TelemetryPacket):
        """Fired by the Event Bus. Continuously records history for all cars."""
        self._latest_telemetry[packet.driver_id] = packet
        
        drv = packet.driver_id
        # Initialize history buffers for this driver if they don't exist yet
        if drv not in self.driver_histories:
            from collections import deque
            self.driver_histories[drv] = {
                'distances': deque(), 'times': deque(),
                'speeds': deque(), 'throttles': deque(),
                'brakes': deque(), 'gears': deque(),
                'rpms': deque()
            }
            self._last_lap_distance[drv] = -1.0
        
        hist = self.driver_histories[drv]
        
        try:
            d = packet.lap_distance
            t = packet.session_time
            s = packet.speed_kmh
            thr = packet.throttle_pct
            brk = packet.brake_pct
            g = packet.gear
            r = packet.rpm

            # --- Lap detection + Ghost Lap backup ---
            # When distance drops by >1000m, the car has crossed the finish line.
            # Small backward movements from crashes/reversing are ignored.
            if self._last_lap_distance.get(drv, -1) - d > 1000:
                # Check if this completed lap is the best so far
                lap_time = packet.last_lap_time
                best = self.best_lap_time.get(drv, float('inf'))
                if lap_time > 0 and lap_time < best:
                    self.best_lap_time[drv] = lap_time
                    # Backup current arrays as reference lap (BEFORE clearing)
                    self.ref_data[drv] = {
                        'distances': list(hist['distances']),
                        'speeds': list(hist['speeds']),
                        'throttles': list(hist['throttles']),
                        'brakes': list(hist['brakes']),
                        'gears': list(hist['gears']),
                        'rpms': list(hist['rpms']),
                    }
                # Clear live arrays for the new lap
                for q in hist.values():
                    q.clear()

            self._last_lap_distance[drv] = d

            hist['distances'].append(d)
            hist['times'].append(t) 
            hist['speeds'].append(s)     
            hist['throttles'].append(thr)
            hist['brakes'].append(brk)      
            hist['gears'].append(g)
            hist['rpms'].append(r)

            self._new_telemetry = True
        except AttributeError as e:
            print(f"⚠️ Missing attribute in telemetry packet: {e}. Discarding to prevent Matplotlib crash.")

    def _on_strategy_alert(self, alert_data: dict):
        """Fired by the Event Bus. Pushes the alert into the thread-safe queue."""
        self._alerts_queue.put(alert_data)

    # --- UI RENDERING LOOP (Runs on Main UI Thread, capped at ~10 FPS) ---
    
    def _render_loop(self):
        """Updates the screen at 10 Hz max, reading from internal buffers.
        
        Only calls expensive matplotlib operations (set_data + draw_idle)
        when new telemetry data has actually arrived, saving CPU when the
        laptop is idling or processing race strategy.
        """
        
        # 0. Skinny CTk updates that are cheap — always do these
        self._drain_alerts()

        # 2. Expensive matplotlib — only when fresh telemetry arrived
        if self._new_telemetry:
            self._new_telemetry = False
            self._update_graph()
            self._update_track_map()

        # 3. Schedule the next frame
        self.after(100, self._render_loop)

    def _drain_alerts(self):
        """Drain strategy alerts onto the console (fast, no matplotlib)."""
        while not self._alerts_queue.empty():
            alert = self._alerts_queue.get_nowait()
            msg = f"[{alert['timestamp']:.1f}s] {alert['message']}\n"
            self.txt_console.configure(state="normal")
            self.txt_console.insert("end", msg)
            self.txt_console.yview("end") 
            self.txt_console.configure(state="disabled")

    def _update_graph(self):
        """Point graph data references and redraw matplotlib lines."""
        d1 = "VER"

        if d1 in self.driver_histories:
            self.telemetry_graph.data[d1] = self.driver_histories[d1]

        # Push reference lap data for ghost rendering
        self.telemetry_graph.ref_data = self.ref_data

        # Push latest packet for tyre widget
        if d1 in self._latest_telemetry:
            self.telemetry_graph.latest_packet = self._latest_telemetry[d1]

        self.telemetry_graph.update_plots()

    def _update_track_map(self):
        """Push positions to the embedded radar display."""
        self.telemetry_graph.update_positions(self._latest_telemetry)

    def _load_track_metadata(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        json_path = os.path.join(project_root, 'data', 'track_metadata.json')
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading track metadata: {e}")
            return {}

