import socket
import threading
import struct
from infrastructure.event_bus import global_event_bus
from core.models import TelemetryPacket

COMPOUND_MAP = {
    0: 'Hyper Soft', 1: 'Ultra Soft', 2: 'Super Soft', 3: 'Soft',
    4: 'Medium', 5: 'Hard', 6: 'Super Hard', 7: 'Inter', 8: 'Wet'
}

class F12018Adapter:
    def __init__(self, host='0.0.0.0', port=20777):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.running = False
        self.thread = None
        
        # Persistent state buffer — never sends None values to the UI
        self.current_state = {
            'x': 0.0,
            'y': 0.0,
            'speed': 0,
            'gear': 0,
            'throttle_pct': 0.0,
            'brake_pct': 0.0,
            'rpm': 0,
            'lap_distance': 0.0,
            'last_lap_time': 0.0,
            'session_time': 0.0,
            'world_x': 0.0,
            'world_z': 0.0,
            'player_car_index': 0,
            'grid_x': [],
            'grid_z': [],
            'g_force_lat': 0.0,
            'g_force_lon': 0.0,
            'brakes_temp': [0, 0, 0, 0],
            'fuel_in_tank': 0.0,
            'ers_percent': 0.0,
            'ers_mode_str': '',
            'current_lap_time': 0.0,
            'sector1_time': 0.0,
            'sector2_time': 0.0,
            'pit_status': 0,
            'tyres_wear': [0, 0, 0, 0],
            'tyres_surface_temp': [0, 0, 0, 0],
            'tyres_inner_temp': [0, 0, 0, 0],
            'tyre_compound': 0,
            'tyre_compound_str': '',
            'aero_damage': (0, 0, 0),
            'weather_str': 'UNKNOWN',
            'track_temp': 0,
            'air_temp': 0,
            'fia_flag': 0,
            'drs_open': False
        }

        # F1 2018 per-car struct sizes
        self.MOTION_CAR_SIZE = 60
        self.LAPDATA_CAR_SIZE = 41
        self.TELEMETRY_CAR_SIZE = 53
        self.CARSTATUS_CAR_SIZE = 52

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"📡 F1 2018 adapter listening on {self.host}:{self.port}...")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1500)

                header_format = '<HBBQfIB'
                header_size = struct.calcsize(header_format)

                if len(data) < header_size:
                    continue

                header = struct.unpack(header_format, data[:header_size])
                packet_id = header[2]
                self.current_state['session_time'] = float(header[4])
                player_idx = header[6]

                # 0. PACKET 0: Motion Data → 3D world coordinates from the game
                # F1 2018: MotionData struct = 60 bytes/car.
                # m_worldPositionX (offset 0), m_worldPositionY (offset 4), m_worldPositionZ (offset 8)
                if packet_id == 0:
                    car_offset = header_size + (player_idx * self.MOTION_CAR_SIZE)
                    if len(data) >= car_offset + 12:
                        world_x, world_y, world_z = struct.unpack(
                            '<fff', data[car_offset:car_offset + 12]
                        )
                        self.current_state['world_x'] = float(world_x)
                        self.current_state['world_z'] = float(world_z)
                    # G-Forces at offsets 36 (m_gForceLateral) and 40 (m_gForceLongitudinal)
                    gforce_offset = car_offset + 36
                    if len(data) >= gforce_offset + 8:
                        g_force_lat, g_force_lon = struct.unpack(
                            '<ff', data[gforce_offset:gforce_offset + 8]
                        )
                        self.current_state['g_force_lat'] = float(g_force_lat)
                        self.current_state['g_force_lon'] = float(g_force_lon)

                    n_cars = (len(data) - header_size) // self.MOTION_CAR_SIZE
                    grid_x = []
                    grid_z = []
                    for i in range(min(20, n_cars)):
                        co = header_size + (i * self.MOTION_CAR_SIZE)
                        wx, _, wz = struct.unpack('<fff', data[co:co + 12])
                        grid_x.append(float(wx))
                        grid_z.append(float(wz))
                    self.current_state['grid_x'] = grid_x
                    self.current_state['grid_z'] = grid_z
                    self.current_state['player_car_index'] = player_idx

                # 1. PACKET 2: Lap Data → lap times, sectors, pit status
                # F1 2018: LapData struct = 41 bytes/car
                #   offset  0: float  m_lastLapTime
                #   offset  4: float  m_currentLapTime
                #   offset  8: float  m_bestLapTime  (ignored)
                #   offset 12: float  m_sector1Time
                #   offset 16: float  m_sector2Time
                #   offset 20: float  m_lapDistance
                #   offset 34: uint8  m_pitStatus  (0=on track, 1=pit lane, 2=garage)
                if packet_id == 2:
                    car_offset = header_size + (player_idx * self.LAPDATA_CAR_SIZE)
                    # Read m_lastLapTime at offset +0
                    if len(data) >= car_offset + 4:
                        last_lap_time, = struct.unpack('<f', data[car_offset:car_offset + 4])
                        self.current_state['last_lap_time'] = float(last_lap_time)
                    # Read m_currentLapTime at offset +4
                    if len(data) >= car_offset + 8:
                        current_lap_time, = struct.unpack('<f', data[car_offset + 4:car_offset + 8])
                        self.current_state['current_lap_time'] = float(current_lap_time)
                    # Read m_sector1Time at offset +12
                    if len(data) >= car_offset + 16:
                        sector1_time, = struct.unpack('<f', data[car_offset + 12:car_offset + 16])
                        self.current_state['sector1_time'] = float(sector1_time)
                    # Read m_sector2Time at offset +16
                    if len(data) >= car_offset + 20:
                        sector2_time, = struct.unpack('<f', data[car_offset + 16:car_offset + 20])
                        self.current_state['sector2_time'] = float(sector2_time)
                    # Read lap distance at offset +20
                    lap_dist_offset = car_offset + 20
                    if len(data) >= lap_dist_offset + 4:
                        lap_distance, = struct.unpack('<f', data[lap_dist_offset:lap_dist_offset + 4])
                        self.current_state['lap_distance'] = float(lap_distance)
                    # Read m_pitStatus at offset +34
                    if len(data) >= car_offset + 35:
                        pit_status, = struct.unpack('<B', data[car_offset + 34:car_offset + 35])
                        self.current_state['pit_status'] = int(pit_status)

                # 2. PACKET 6: Car Telemetry → real car values + temperatures
                # F1 2018 CarTelemetryData struct = 53 bytes/car.
                # First 9 bytes: speed(uint16), throttle(uint8), steer(int8),
                # brake(uint8), clutch(uint8), gear(int8), engineRPM(uint16)  ← F1 2018 uses integers, NOT floats
                # From offset 11: m_brakesTemperature[4] (uint16[4] = 8B)
                # From offset 19: m_tyresSurfaceTemperature[4] (uint16[4] = 8B)
                # From offset 27: m_tyresInnerTemperature[4] (uint16[4] = 8B)
                # offset 35: m_engineTemperature (uint16), offset 37: m_tyresPressure[4] (float[4])
                # NOTE: In F1 2018 temperatures are uint16, NOT uint8 (changed in F1 2020)
                # NOTE: F1 2018 does NOT have m_revLightsBitValue or m_surfaceType
                if packet_id == 6:
                    car_offset = header_size + (player_idx * self.TELEMETRY_CAR_SIZE)
                    if len(data) >= car_offset + 9:
                        fields = struct.unpack('<HBbBBbH', data[car_offset:car_offset + 9])
                        print(f"  Real pedal values -> Accel: {fields[1]} | Brake: {fields[3]} | Gear: {fields[5]}")
                        self.current_state['speed'] = int(fields[0])                       # uint16
                        self.current_state['throttle_pct'] = float(fields[1])              # uint8 0-100 directo
                        # fields[2] = steer (int8) – ignorado
                        self.current_state['brake_pct'] = float(fields[3])                 # uint8 0-100 directo
                        # fields[4] = clutch (uint8) – ignorado
                        self.current_state['gear'] = int(fields[5])                        # int8
                        self.current_state['rpm'] = int(fields[6])                         # uint16
                    # Read DRS (uint8 @ offset 9)
                    drs_offset = car_offset + 9
                    if len(data) >= drs_offset + 1:
                        drs_value, = struct.unpack('<B', data[drs_offset:drs_offset + 1])
                        self.current_state['drs_open'] = bool(drs_value)
                    # Read brake temperatures (4 uint16 @ offset 11)
                    brake_temp_offset = car_offset + 11
                    if len(data) >= brake_temp_offset + 8:
                        brake_temps = struct.unpack_from('<HHHH', data, brake_temp_offset)
                        self.current_state['brakes_temp'] = [float(t) for t in brake_temps]
                    # Read tyre surface temperatures (4 uint16 @ offset 19)
                    tyre_temp_offset = car_offset + 19
                    if len(data) >= tyre_temp_offset + 8:
                        temps = struct.unpack_from('<HHHH', data, tyre_temp_offset)
                        self.current_state['tyres_surface_temp'] = [float(t) for t in temps]
                    # Read tyre inner (core) temperatures (4 uint16 @ offset 27)
                    inner_temp_offset = car_offset + 27
                    if len(data) >= inner_temp_offset + 8:
                        inner_temps = struct.unpack_from('<HHHH', data, inner_temp_offset)
                        self.current_state['tyres_inner_temp'] = [float(t) for t in inner_temps]
                # 3. PACKET 7: Car Status → tyre wear, fuel, ERS
                # F1 2018 CarStatusData struct = 52 bytes/car (packed, no padding).
                if packet_id == 7:
                    car_data_start = 21 + (player_idx * self.CARSTATUS_CAR_SIZE)
                    # Fuel (float @ offset +5)
                    fuel_offset = car_data_start + 5
                    if len(data) >= fuel_offset + 4:
                        fuel_in_tank, = struct.unpack_from('<f', data, fuel_offset)
                        self.current_state['fuel_in_tank'] = float(fuel_in_tank)
                    # ERS store energy (float @ offset +35)
                    ers_energy_offset = car_data_start + 35
                    if len(data) >= ers_energy_offset + 4:
                        ers_store, = struct.unpack_from('<f', data, ers_energy_offset)
                        self.current_state['ers_percent'] = min(100.0, (float(ers_store) / 4000000.0) * 100.0)
                    # ERS deploy mode (uint8 @ offset +39)
                    ers_mode_offset = car_data_start + 39
                    ERS_MODE_MAP = {0: 'None', 1: 'Low', 2: 'Medium', 3: 'High', 4: 'Overtake', 5: 'Hotlap'}
                    if len(data) >= ers_mode_offset + 1:
                        mode_raw, = struct.unpack_from('<B', data, ers_mode_offset)
                        self.current_state['ers_mode_str'] = ERS_MODE_MAP.get(int(mode_raw), 'Unknown')
                    # Tyres wear (4 uint8 @ offset +19)
                    wear_offset = car_data_start + 19
                    if len(data) >= wear_offset + 4:
                        tyres_wear = struct.unpack_from('<4B', data, wear_offset)
                        RL, RR, FL, FR = tyres_wear
                        self.current_state['tyres_wear'] = [RL, RR, FL, FR]
                    # Tyre compound (uint8 @ offset +23)
                    compound_offset = car_data_start + 23
                    if len(data) >= compound_offset + 1:
                        compound, = struct.unpack_from('<B', data, compound_offset)
                        self.current_state['tyre_compound'] = int(compound)
                        self.current_state['tyre_compound_str'] = COMPOUND_MAP.get(int(compound), 'Unknown')
                    # FIA flag (int8 @ offset +34)
                    flag_offset = car_data_start + 34
                    if len(data) >= flag_offset + 1:
                        fia_flag, = struct.unpack_from('<b', data, flag_offset)
                        self.current_state['fia_flag'] = int(fia_flag)
                    # Aero damage (3 uint8 @ offsets +28, +29, +30)
                    if len(data) >= car_data_start + 31:
                        fl_w, fr_w, r_w = struct.unpack_from('<BBB', data, car_data_start + 28)
                        self.current_state['aero_damage'] = (int(fl_w), int(fr_w), int(r_w))

                # 5. PACKET 1: Session Data → weather, track/air temperature
                # F1 2018: Session data starts at byte 21 (after header).
                #   offset  0: uint8  m_weather
                #   offset  1: int8   m_trackTemperature
                #   offset  2: int8   m_airTemperature
                WEATHER_MAP = {
                    0: 'CLEAR', 1: 'LIGHT CLOUD', 2: 'OVERCAST',
                    3: 'LIGHT RAIN', 4: 'HEAVY RAIN', 5: 'STORM'
                }
                if packet_id == 1:
                    if len(data) >= 24:
                        weather_raw, track_temp, air_temp = struct.unpack_from('<B b b', data, 21)
                        self.current_state['weather_str'] = WEATHER_MAP.get(int(weather_raw), 'UNKNOWN')
                        self.current_state['track_temp'] = int(track_temp)
                        self.current_state['air_temp'] = int(air_temp)

                # 4. Send complete packet to the UI (never None)
                # Skip Motion-only packets to avoid flooding the bus;
                # world_x/world_z are retained in current_state for the next send.
                if packet_id == 0:
                    continue
                # Skip Car Status-only packets (data already stored)
                if packet_id == 7:
                    continue
                # Skip Session Data-only packets (no car-specific data)
                if packet_id == 1:
                    continue

                payload = TelemetryPacket(
                    source="F1_2018",
                    session_time=self.current_state['session_time'],
                    last_lap_time=self.current_state['last_lap_time'],
                    driver_id='VER',
                    speed_kmh=self.current_state['speed'],
                    throttle_pct=self.current_state['throttle_pct'],
                    brake_pct=self.current_state['brake_pct'],
                    gear=self.current_state['gear'],
                    rpm=self.current_state['rpm'],
                    lap_distance=self.current_state['lap_distance'],
                    x_pos=self.current_state['x'],
                    y_pos=self.current_state['y'],
                    x=self.current_state['x'],
                    y=self.current_state['y'],
                    world_x=self.current_state['world_x'],
                    world_z=self.current_state['world_z'],
                    player_car_index=self.current_state['player_car_index'],
                    grid_x=self.current_state['grid_x'],
                    grid_z=self.current_state['grid_z'],
                    g_force_lat=self.current_state['g_force_lat'],
                    g_force_lon=self.current_state['g_force_lon'],
                    brakes_temp=self.current_state['brakes_temp'],
                    current_lap_time=self.current_state['current_lap_time'],
                    sector1_time=self.current_state['sector1_time'],
                    sector2_time=self.current_state['sector2_time'],
                    pit_status=self.current_state['pit_status'],
                    fuel_in_tank=self.current_state['fuel_in_tank'],
                    ers_percent=self.current_state['ers_percent'],
                    ers_mode_str=self.current_state['ers_mode_str'],
                    tyres_wear=self.current_state['tyres_wear'],
                    tyres_surface_temp=self.current_state['tyres_surface_temp'],
                    tyres_inner_temp=self.current_state['tyres_inner_temp'],
                    tyre_compound=self.current_state['tyre_compound'],
                    tyre_compound_str=self.current_state['tyre_compound_str'],
                    aero_damage=self.current_state['aero_damage'],
                    weather_str=self.current_state['weather_str'],
                    track_temp=self.current_state['track_temp'],
                    air_temp=self.current_state['air_temp'],
                    fia_flag=self.current_state['fia_flag'],
                    drs_open=self.current_state['drs_open']
                )

                global_event_bus.publish('TELEMETRY_UPDATE', payload)

            except Exception as e:
                print(f"⚠️ Error reading F1 2018 UDP stream: {e}")
                continue