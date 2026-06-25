from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TelemetryPacket:
    """
    Universal telemetry schema representing a single car's state at time T.
    Acts as the standard data transfer object (DTO) across all adapters.
    """
    
    # Metadata
    source: str = ""          # Target values: "F1_LIVE" or "F1_GAME"
    session_time: float = 0.0 # Seconds elapsed since the session started
    last_lap_time: float = 0.0  # Last completed lap time in seconds (0.0 = no lap yet)
    driver_id: str = ""   # 3-Letter code: "VER", "ALO", "HAM"
    
    # Timing data (from Packet 2 — Lap Data)
    current_lap_time: float = 0.0
    sector1_time: float = 0.0
    sector2_time: float = 0.0
    pit_status: int = 0  # 0=on track, 1=pit lane, 2=garage

    # Dynamic Telemetry (High frequency - 60Hz)
    speed_kmh: int = 0        # Car speed in km/h
    throttle_pct: float = 0.0 # Throttle pedal application (0.0-100.0%)
    brake_pct: float = 0.0    # Brake pedal application (0.0-100.0%)
    gear: int = 0             # Current gear (0=Neutral, 1-8=Forward, -1=Reverse)
    rpm: int = 0              # Engine revolutions per minute
    
    # Positioning and Tracking
    lap_distance: float = 0.0 # Distance traveled in the current lap (meters)
    x_pos: Optional[float] = None
    y_pos: Optional[float] = None
    
    # Track & Weather Conditions (Optional / Event-driven updates)
    track_temp: int = 0
    air_temp: int = 0
    weather_str: str = 'UNKNOWN'

    # FIA Flag status (from Packet 7 — Car Status)
    fia_flag: int = 0  # -1=None, 0=None, 1=Green, 2=Blue, 3=Yellow, 4=Red

    #Track position
    x: float = 0.0
    y: float = 0.0

    # Game world coordinates (Packet 0 - Motion Data)
    world_x: float = 0.0
    world_z: float = 0.0

    # Full grid positions (all 20 cars, from Packet 0)
    player_car_index: int = 0
    grid_x: list = field(default_factory=list)
    grid_z: list = field(default_factory=list)

    # G-Force data (from Packet 0 — Motion Data)
    g_force_lat: float = 0.0
    g_force_lon: float = 0.0

    # Energy management (from Packet 7 — Car Status)
    fuel_in_tank: float = 0.0
    ers_percent: float = 0.0
    ers_mode_str: str = ''

    # Brake temperatures (order: RL, RR, FL, FR — from Packet 6)
    brakes_temp: list = field(default_factory=lambda: [0, 0, 0, 0])

    # Tyre data (order: RL, RR, FL, FR — per F1 2018 convention)
    tyres_wear: list = field(default_factory=lambda: [0, 0, 0, 0])
    tyres_surface_temp: list = field(default_factory=lambda: [0, 0, 0, 0])
    tyres_inner_temp: list = field(default_factory=lambda: [0, 0, 0, 0])
    tyre_compound: int = 0
    tyre_compound_str: str = ''

    # DRS status (from Packet 6 — Car Telemetry)
    drs_open: bool = False

    # Aero damage (from Packet 7 — Car Status)
    aero_damage: tuple = (0, 0, 0)  # (fl_wing, fr_wing, rear_wing) 0-100%

