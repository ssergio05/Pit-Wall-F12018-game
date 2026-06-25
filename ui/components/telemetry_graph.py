import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch
from collections import deque
from typing import Dict
import matplotlib.pyplot as plt
import math
import json
import os
import time
import csv
import subprocess
import sys
import tkinter as tk
from tkinter import simpledialog

from matplotlib.widgets import Button

from core.models import TelemetryPacket
from core.dss_alerts import evaluate_dss_alerts

plt.style.use('dark_background')

# Official F1 Team HEX Colors
DRIVER_COLORS = {
    "VER": "#3671C6", "PER": "#3671C6", # Red Bull (Dark Blue)
    "HAM": "#27F4D2", "RUS": "#27F4D2", # Mercedes (Teal)
    "LEC": "#E80020", "SAI": "#E80020", # Ferrari (Red)
    "NOR": "#FF8000", "PIA": "#FF8000", # McLaren (Papaya Orange)
    "ALO": "#229971", "STR": "#229971", # Aston Martin (British Racing Green)
    "GAS": "#FF87BC", "OCO": "#FF87BC", # Alpine (Pink/Blue)
    "ALB": "#005AFF", "SAR": "#005AFF", # Williams (Bright Blue)
    "TSU": "#6692FF", "RIC": "#6692FF", # RB (Hugo Boss Blue)
    "BOT": "#52E252", "ZHO": "#52E252", # Sauber (Neon Green)
    "MAG": "#FFFFFF", "HUL": "#FFFFFF"  # Haas (White)
}

class LiveTelemetryGraph(ctk.CTkFrame):
    """
    Single-driver telemetry visualization panel using Matplotlib.

    Renders speed, throttle, brake, gear, and RPM traces along the track
    distance axis, with an embedded radar track map, G-force meter, tyre
    condition widget, and energy management bars.

    Args:
        master: Parent tkinter/CTk widget.
        driver_1: Three-letter driver code (e.g. "VER") for the player car.
        max_points: Maximum data points retained per telemetry channel.
        track_metadata: Dictionary of circuit metadata for corner markers.
    """
    def __init__(self, master, driver_1="VER", max_points=3000, track_metadata=None, **kwargs):
        super().__init__(master, **kwargs)

        self.driver_1 = driver_1
        self.max_points = max_points

        self.c1 = DRIVER_COLORS.get(self.driver_1, "#00FFFF")

        self._corner_artists = []

        # Reference lap data for ghost rendering (populated by PitWallDashboard)
        self.ref_data: Dict[str, Dict[str, list]] = {}

        self.data = {
            self.driver_1: {'distances': deque(maxlen=self.max_points),
                            'speeds': deque(maxlen=self.max_points), 'throttles': deque(maxlen=self.max_points),
                            'brakes': deque(maxlen=self.max_points), 'gears': deque(maxlen=self.max_points),
                            'rpms': deque(maxlen=self.max_points)}
        }

        # Radar transformation state
        self.rotation_rad = 0.0
        self.flip_x = False
        self.flip_z = False

        # --- Figure with GridSpec: 5 rows, 4 columns ---
        # Telemetry uses left 3 cols, right col for radar/gforce/tyres
        self.fig = Figure(figsize=(14, 8), dpi=100, facecolor='#1e1e1e')

        gs = GridSpec(5, 4, figure=self.fig, width_ratios=[1, 1, 1, 1.2])
        gs.update(left=0.06, right=0.94, top=0.88, bottom=0.08, hspace=0.35, wspace=0.25)

        # --- Row 0: Speed ---
        self.ax_speed = self.fig.add_subplot(gs[0, :3])
        self.ax_speed.set_ylabel("Speed (km/h)")
        self.ax_speed.set_ylim(0, 360)
        self.ax_speed.grid(True, linestyle=':', alpha=0.3)

        self.l_spd_1, = self.ax_speed.plot([], [], color=self.c1, linewidth=2)
        self.drs_text = self.fig.text(0.70, 0.03, ' DRS ', color='gray', fontsize=11, family='monospace', ha='left', va='center', weight='bold', bbox=dict(facecolor='black', edgecolor='gray', boxstyle='round,pad=0.3'))

        # --- Row 1: Throttle ---
        self.ax_throttle = self.fig.add_subplot(gs[1, :3], sharex=self.ax_speed)
        self.ax_throttle.set_ylabel("Throttle (%)")
        self.ax_throttle.set_ylim(-5, 105)
        self.ax_throttle.grid(True, linestyle=':', alpha=0.3)
        self.l_thr_1, = self.ax_throttle.plot([], [], color=self.c1, linewidth=2)

        # --- Row 2: Brake ---
        self.ax_brake = self.fig.add_subplot(gs[2, :3], sharex=self.ax_speed)
        self.ax_brake.set_ylabel("Brake (%)")
        self.ax_brake.set_ylim(-5, 105)
        self.ax_brake.grid(True, linestyle=':', alpha=0.3)
        self.l_brk_1, = self.ax_brake.plot([], [], color=self.c1, linewidth=2)

        # --- Row 3: Gear / RPM (twinx) ---
        self.ax_trans = self.fig.add_subplot(gs[3, :3], sharex=self.ax_speed)
        self.ax_trans.set_ylabel("Gear")
        self.ax_trans.set_ylim(0, 9)
        self.ax_trans.set_xlabel("Track Distance (m)")
        self.ax_trans.grid(True, linestyle=':', alpha=0.3)

        self.ax_rpm = self.ax_trans.twinx()
        self.ax_rpm.set_ylabel("RPM")
        self.ax_rpm.set_ylim(0, 15000)

        self.l_gear_1, = self.ax_trans.plot([], [], color=self.c1, linewidth=2, drawstyle='steps-post')

        self.l_rpm_1, = self.ax_rpm.plot([], [], color=self.c1, linewidth=1, alpha=0.4)

        # --- Ghost lines (reference best lap, drawn behind live data with low zorder) ---
        self.l_spd_ghost, = self.ax_speed.plot([], [], color='gray', alpha=0.4, linestyle='--', linewidth=1.5, zorder=1)
        self.l_thr_ghost, = self.ax_throttle.plot([], [], color='gray', alpha=0.4, linestyle='--', linewidth=1.5, zorder=1)
        self.l_brk_ghost, = self.ax_brake.plot([], [], color='gray', alpha=0.4, linestyle='--', linewidth=1.5, zorder=1)
        self.l_gear_ghost, = self.ax_trans.plot([], [], color='gray', alpha=0.4, linestyle='--', linewidth=1.5, drawstyle='steps-post', zorder=1)
        self.l_rpm_ghost, = self.ax_rpm.plot([], [], color='gray', alpha=0.4, linestyle='--', linewidth=1, zorder=1)

        # --- Radar subplot (right column, rows 0-1) ---
        self.ax_radar = self.fig.add_subplot(gs[0:2, 3])
        self.ax_radar.set_facecolor('#1e1e1e')
        self.ax_radar.axis('off')
        self._setup_radar_artists()

        # --- G-Force meter (right column, row 2) ---
        self.ax_gforce = self.fig.add_subplot(gs[2, 3])
        self._setup_gforce_artists()

        # --- Tyre wear / temperature widget (right column, rows 3-4) ---
        self.ax_tyres = self.fig.add_subplot(gs[3:5, 3])
        self._setup_tyre_artists()

        # --- Energy management bar (bottom-left, row 4, cols 0-1) ---
        self.ax_energy = self.fig.add_subplot(gs[4, :2])
        self._setup_energy_artists()

        # --- Timing ticker (horizontal bar at the very bottom) ---
        base_y = 0.03
        props = dict(color='white', fontsize=11, fontfamily='monospace', ha='left', va='center',
                     transform=self.fig.transFigure)
        self.txt_last = self.fig.text(0.02, base_y, '', **props)
        self.txt_curr = self.fig.text(0.18, base_y, '', **props)
        self.txt_s1 = self.fig.text(0.34, base_y, '', **props)
        self.txt_s2 = self.fig.text(0.46, base_y, '', **props)
        self.txt_s3 = self.fig.text(0.58, base_y, '', **props)
        self.best_s1 = 999.0
        self.best_s2 = 999.0
        self.best_lap = 999.0
        self.saved_last_lap = 0.0
        self.freeze_until = 0.0
        self.saved_s1 = 0.0
        self.saved_s2 = 0.0

        # --- Weather / track conditions header (top-center) ---
        self.weather_text = self.fig.text(
            0.5, 0.95, '', color='white', fontsize=12,
            ha='center', va='top', weight='bold',
            transform=self.fig.transFigure
        )

        # --- Aero damage monitor (above tyre widget) ---
        self.damage_text = self.fig.text(
            0.85, 0.40, '', color='#AAAAAA', fontsize=9,
            ha='center', va='center', weight='bold',
            transform=self.fig.transFigure
        )

        # Latest telemetry packet for tyre data (set by PitWallDashboard)
        self.latest_packet: TelemetryPacket = None

        # --- Circuit selector (CTkComboBox) ---
        self.track_metadata = track_metadata or {}
        self.available_circuits = list(self.track_metadata.keys()) if self.track_metadata else []
        self.current_track_key = self.available_circuits[0] if self.available_circuits else None

        self.top_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        self.top_frame.pack(side="top", fill="x", padx=10, pady=(2, 0))

        self.circuit_label = ctk.CTkLabel(
            self.top_frame, text="Circuit:", font=("Helvetica", 12, "bold")
        )
        self.circuit_label.pack(side="left", padx=(0, 5))

        self.circuit_combo = ctk.CTkComboBox(
            self.top_frame,
            values=self.available_circuits if self.available_circuits else ["N/A"],
            command=self._on_circuit_changed,
            width=220
        )
        self.circuit_combo.pack(side="left")

        # Initialize first circuit
        if self.available_circuits:
            first_circ = self.available_circuits[0]
            self.circuit_combo.set(first_circ)
            self.set_track(self.track_metadata[first_circ])
            self.init_radar(first_circ, self.track_metadata)

        # --- Replay Session Button ---
        self.ax_replay_btn = self.fig.add_axes([0.05, 0.92, 0.15, 0.04])
        self.replay_btn = Button(self.ax_replay_btn, 'Replay Session', color='#333333', hovercolor='#555555')
        self.replay_btn.label.set_color('white')
        self.replay_btn.label.set_weight('bold')
        for spine in self.ax_replay_btn.spines.values():
            spine.set_edgecolor('#777777')

        def launch_replay(event):
            try:
                subprocess.Popen(["python", "replay_viewer.py"])
            except Exception as e:
                print(f"Error launching Replay Viewer: {e}")

        self.replay_btn.on_clicked(launch_replay)

        # --- CSV Black Box (Data Logger) ---
        self.current_csv_filename = 'temp_telemetry.csv'
        self.csv_file = open(self.current_csv_filename, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['Timestamp', 'LapTime', 'Speed', 'Throttle', 'Brake', 'Gear', 'DRS', 'FL_Wear', 'FR_Wear', 'RL_Wear', 'RR_Wear'])
        self.fig.canvas.mpl_connect('close_event', self.on_close)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        # DSS Alert pop-ups (pool of 4 stacked banners, hidden by default)
        self.dss_popups = []
        for _ in range(4):
            txt = self.fig.text(
                0.98, 0.98, '',
                ha='right', va='top', visible=False,
                color='white', fontsize=10, fontweight='bold', fontfamily='monospace',
                zorder=100, transform=self.fig.transFigure
            )
            self.dss_popups.append(txt)

    def _setup_radar_artists(self):
        """Initialise radar plot artists: track line, player dot, grid dots, and empty-state text."""
        self.track_line, = self.ax_radar.plot([], [], color='#444444', linewidth=3, zorder=1)

        self.player_dot, = self.ax_radar.plot([], [], 'o', color='#FF4444', markersize=16,
                                                markeredgecolor='white', markeredgewidth=1.5, zorder=15)

        self.grid_dots = []
        for _ in range(20):
            dot, = self.ax_radar.plot([], [], 'o', color='#AAAAAA', markersize=5, alpha=0.5, zorder=8, visible=False)
            self.grid_dots.append(dot)

        self.empty_text = self.ax_radar.text(
            0.5, 0.5, '', color='#666666', fontsize=14,
            ha='center', va='center', transform=self.ax_radar.transAxes
        )

    def _setup_gforce_artists(self):
        """Initialise the G-force traction circle with axis lines, reference circles, and the data dot."""
        self.ax_gforce.set_facecolor('#1e1e1e')
        self.ax_gforce.set_xlim(-5, 5)
        self.ax_gforce.set_ylim(-5, 5)
        self.ax_gforce.set_aspect('equal')
        self.ax_gforce.set_xticks([])
        self.ax_gforce.set_yticks([])
        for spine in self.ax_gforce.spines.values():
            spine.set_visible(False)

        self.ax_gforce.axhline(0, color='#444444', linewidth=0.8, alpha=0.6)
        self.ax_gforce.axvline(0, color='#444444', linewidth=0.8, alpha=0.6)

        circle = plt.Circle((0, 0), 4.0, fill=False, edgecolor='#555555',
                            linewidth=1.5, linestyle='--', alpha=0.5)
        self.ax_gforce.add_patch(circle)

        inner = plt.Circle((0, 0), 2.0, fill=False, edgecolor='#444444',
                           linewidth=0.8, linestyle=':', alpha=0.3)
        self.ax_gforce.add_patch(inner)

        self.gforce_dot, = self.ax_gforce.plot(
            [], [], 'o', color='#FF4444', markersize=12,
            markeredgecolor='white', markeredgewidth=1.5, zorder=10
        )

        self.ax_gforce.text(0.5, 0.95, 'G-FORCE', color='#AAAAAA', fontsize=9,
                            fontweight='bold', ha='center', va='top',
                            transform=self.ax_gforce.transAxes)

    def on_close(self, event):
        """Handle graph window close: save CSV, prompt for filename, then force exit."""
        if hasattr(self, 'csv_file') and not self.csv_file.closed:
            self.csv_file.close()

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        new_name = simpledialog.askstring("Save Telemetry", "Session name (e.g. 'Practice1_Australia'):", parent=root)
        root.quit()
        root.destroy()

        if new_name:
            if not new_name.lower().endswith('.csv'):
                new_name += '.csv'
            final_name = new_name
            counter = 1
            while os.path.exists(final_name):
                final_name = f"{new_name.replace('.csv', '')}_{counter}.csv"
                counter += 1
            try:
                os.rename(self.current_csv_filename, final_name)
                print(f"Telemetry saved successfully as: {final_name}")
            except Exception as e:
                print(f"Error renaming file: {e}")
        else:
            print("Save cancelled or empty name. Keeping 'temp_telemetry.csv'.")

        print("🧹 Cleaning up background processes...")
        os._exit(0)

    def _update_gforce(self):
        """Update the G-force dot position from the latest packet's lateral/longitudinal G data."""
        if self.latest_packet is None:
            return
        lat = getattr(self.latest_packet, 'g_force_lat', 0.0)
        lon = getattr(self.latest_packet, 'g_force_lon', 0.0)
        self.gforce_dot.set_data([lat], [lon])

    def _update_weather(self):
        """Update the weather/track conditions header with current data from the packet."""
        if self.latest_packet is None:
            return
        p = self.latest_packet
        weather = getattr(p, 'weather_str', 'UNKNOWN')
        track = getattr(p, 'track_temp', 0)
        air = getattr(p, 'air_temp', 0)
        self.weather_text.set_text(f'WEATHER: {weather} | TRACK: {track}°C | AIR: {air}°C')
        rain_ids = {'LIGHT RAIN', 'HEAVY RAIN', 'STORM'}
        if weather in rain_ids:
            self.weather_text.set_color('#00BFFF')
        else:
            self.weather_text.set_color('#00FF00')

    def _update_damage(self):
        """Update the aero damage display and colour-code it by severity."""
        if self.latest_packet is None:
            return
        fl, fr, rw = getattr(self.latest_packet, 'aero_damage', (0, 0, 0))
        self.damage_text.set_text(f'AERO: FL {fl}% | FR {fr}% | RW {rw}%')
        if fl > 25 or fr > 25 or rw > 25:
            self.damage_text.set_color('red')
        elif fl > 0 or fr > 0 or rw > 0:
            self.damage_text.set_color('yellow')
        else:
            self.damage_text.set_color('#AAAAAA')

    def _setup_energy_artists(self):
        """Initialise the ERS and Fuel horizontal bar artists."""
        self.ax_energy.set_facecolor('#1e1e1e')
        self.ax_energy.set_xlim(0, 100)
        self.ax_energy.set_ylim(0, 2)
        self.ax_energy.axis('off')

        # ERS bar (top)
        self.ers_bar = self.ax_energy.barh(1.5, 0, height=0.5, color='#FFB000', left=0)[0]
        self.ers_text = self.ax_energy.text(
            1, 1.5, 'ERS: 0% | MODE: N/A',
            color='white', fontsize=7, fontfamily='monospace',
            ha='left', va='center'
        )
        self.ax_energy.text(0.5, 1.95, 'ERS', color='#FFB000', fontsize=7,
                            fontweight='bold', ha='center', va='top')

        # Fuel bar (bottom)
        self.fuel_bar = self.ax_energy.barh(0.5, 0, height=0.5, color='#00CC00', left=0)[0]
        self.fuel_text = self.ax_energy.text(
            1, 0.5, 'FUEL: 0.0 kg',
            color='white', fontsize=7, fontfamily='monospace',
            ha='left', va='center'
        )
        self.ax_energy.text(0.5, 0.95, 'FUEL', color='#00CC00', fontsize=7,
                            fontweight='bold', ha='center', va='top')

    def _update_energy(self):
        """Update ERS percentage bar and fuel level bar from the latest packet."""
        if self.latest_packet is None:
            return
        ers_pct = getattr(self.latest_packet, 'ers_percent', 0.0)
        ers_mode = getattr(self.latest_packet, 'ers_mode_str', 'N/A')
        fuel = getattr(self.latest_packet, 'fuel_in_tank', 0.0)
        fuel_pct = min(100.0, (fuel / 105.0) * 100.0)

        self.ers_bar.set_width(ers_pct)
        self.ers_text.set_text(f'ERS: {ers_pct:.0f}% | MODE: {ers_mode}')
        self.ers_text.set_x(ers_pct + 1)

        self.fuel_bar.set_width(fuel_pct)
        self.fuel_text.set_text(f'FUEL: {fuel:.1f} kg')
        self.fuel_text.set_x(fuel_pct + 1)

    @staticmethod
    def _format_time(seconds):
        """Convert seconds to mm:ss.ms format, or '--:--.---' if zero/negative."""
        if seconds <= 0:
            return '--:--.---'
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f'{mins}:{secs:02d}.{ms:03d}'

    def _update_timing(self):
        """Update lap-time, sector-time, and best-lap text displays with colour coding."""
        if self.latest_packet is None:
            return
        p = self.latest_packet
        current_t = time.time()

        # Detect finish line crossing
        if p.last_lap_time != self.saved_last_lap and p.last_lap_time > 0:
            self.freeze_until = current_t + 5.0
            self.saved_last_lap = p.last_lap_time
            if p.sector1_time > 0:
                self.saved_s1 = p.sector1_time
            if p.sector2_time > 0:
                self.saved_s2 = p.sector2_time

        # Frozen mode — show last lap + calculate S3
        if current_t < self.freeze_until:
            if p.last_lap_time < self.best_lap:
                self.best_lap = p.last_lap_time
            color = 'lime' if p.last_lap_time <= self.best_lap else 'white'
            self.txt_last.set_text(f'LAST: {self._format_time(p.last_lap_time)}')
            self.txt_last.set_color(color)
            self.txt_curr.set_text('CURR: --:--.---')
            self.txt_curr.set_color('white')

            s3_time = p.last_lap_time - (self.saved_s1 + self.saved_s2)
            if s3_time > 0:
                self.txt_s3.set_text(f'S3: {self._format_time(s3_time)}')
                self.txt_s3.set_color('#FFB000')
            else:
                self.txt_s3.set_text('S3: --:--.---')
                self.txt_s3.set_color('white')
            return

        # Normal mode
        self.txt_last.set_text(f'LAST: {self._format_time(p.last_lap_time)}')
        if p.last_lap_time > 0:
            if p.last_lap_time < self.best_lap:
                self.best_lap = p.last_lap_time
            color = 'lime' if p.last_lap_time <= self.best_lap else 'white'
            self.txt_last.set_color(color)
        else:
            self.txt_last.set_color('white')

        if p.pit_status > 0:
            self.txt_curr.set_text('CURR: IN PIT')
            self.txt_curr.set_color('#FFAA00')
        else:
            self.txt_curr.set_text(f'CURR: {self._format_time(p.current_lap_time)}')
            self.txt_curr.set_color('white')

        if p.sector1_time > 0:
            if p.sector1_time < self.best_s1:
                self.best_s1 = p.sector1_time
            color = 'lime' if p.sector1_time <= self.best_s1 else 'yellow'
            self.txt_s1.set_text(f'S1: {self._format_time(p.sector1_time)}')
            self.txt_s1.set_color(color)
            self.saved_s1 = p.sector1_time
        else:
            self.txt_s1.set_text('S1: --:--.---')
            self.txt_s1.set_color('white')

        if p.sector2_time > 0:
            if p.sector2_time < self.best_s2:
                self.best_s2 = p.sector2_time
            color = 'lime' if p.sector2_time <= self.best_s2 else 'yellow'
            self.txt_s2.set_text(f'S2: {self._format_time(p.sector2_time)}')
            self.txt_s2.set_color(color)
            self.saved_s2 = p.sector2_time
        else:
            self.txt_s2.set_text('S2: --:--.---')
            self.txt_s2.set_color('white')

        self.txt_s3.set_text('S3: --:--.---')
        self.txt_s3.set_color('white')

    def _setup_tyre_artists(self):
        """Initialise the four tyre patches (FL, FR, RL, RR) with default text and colours."""
        self.ax_tyres.set_facecolor('#1e1e1e')
        self.ax_tyres.axis('off')

        # Wheel positions (x, y) in axes coords — front at top, rear at bottom:
        #   [FL] [FR]  ← front (top)
        #   [RL] [RR]  ← rear (bottom)
        wheel_defs = [
            ('FL', 0.05, 0.42),
            ('FR', 0.55, 0.42),
            ('RL', 0.05, -0.03),
            ('RR', 0.55, -0.03),
        ]
        bw, bh = 0.40, 0.35

        self.tyre_patches = []
        self.tyre_texts = []

        for label, x, y in wheel_defs:
            rect = FancyBboxPatch(
                (x, y), bw, bh, boxstyle='round,pad=0.02',
                facecolor='#005500', edgecolor='#888888', linewidth=1
            )
            rect.set_alpha(0.85)
            self.ax_tyres.add_patch(rect)
            self.tyre_patches.append(rect)
            if label == 'FL':
                self.box_fl = rect
            elif label == 'FR':
                self.box_fr = rect
            elif label == 'RL':
                self.box_rl = rect
            elif label == 'RR':
                self.box_rr = rect

            txt = self.ax_tyres.text(
                x + bw / 2, y + bh / 2, f'{label}\nWear: 0%\n0°C / 0°C\nBrake: 0°C',
                color='white', fontsize=6,
                ha='center', va='center'
            )
            self.tyre_texts.append(txt)

        self.tyre_title = self.ax_tyres.text(
            0.5, 0.90, 'TYRES',
            color='#AAAAAA', fontsize=9, fontweight='bold',
            ha='center', va='top', transform=self.ax_tyres.transAxes
        )

        self.ax_tyres.set_xlim(0, 1)
        self.ax_tyres.set_ylim(-0.08, 0.95)

    def _update_tyres(self):
        """Update tyre patch colors and text from latest telemetry packet."""
        if self.latest_packet is None:
            return

        # TelemetryPacket stores arrays as [RL, RR, FL, FR]
        # Display order is [FL, FR, RL, RR]
        src_map = [2, 3, 0, 1]
        labels = ['FL', 'FR', 'RL', 'RR']
        wear = self.latest_packet.tyres_wear
        surf_temps = self.latest_packet.tyres_surface_temp
        core_temps = self.latest_packet.tyres_inner_temp
        brakes = self.latest_packet.brakes_temp

        for i in range(4):
            src = src_map[i]
            w = wear[src] if src < len(wear) else 0
            st = surf_temps[src] if src < len(surf_temps) else 0
            ct = core_temps[src] if src < len(core_temps) else 0
            bt = brakes[src] if src < len(brakes) else 0

            if w < 30:
                color = '#005500'
            elif w < 70:
                color = '#886600'
            else:
                color = '#992222'

            self.tyre_patches[i].set_facecolor(color)
            self.tyre_texts[i].set_text(f'{labels[i]}\nWear: {w}%\n{st:.0f}°C / {ct:.0f}°C\nBrake: {bt:.0f}°C')

        compound_str = getattr(self.latest_packet, 'tyre_compound_str', '')
        self.tyre_title.set_text(f'TYRES - {compound_str}' if compound_str else 'TYRES')

    def _update_dss_alerts(self):
        """Evaluate and display DSS (Decision Support System) alert pop-ups."""
        if self.latest_packet is None:
            for txt in self.dss_popups:
                txt.set_visible(False)
            return
        alerts = evaluate_dss_alerts(self.latest_packet)
        y_start = 0.98
        y_step = 0.05
        for i, txt_obj in enumerate(self.dss_popups):
            if i < len(alerts):
                alert_msg = alerts[i]
                txt_obj.set_text(alert_msg)
                txt_obj.set_y(y_start - i * y_step)
                if '[CRITICAL]' in alert_msg:
                    txt_obj.set_bbox(dict(boxstyle='round,pad=0.3', facecolor='darkred', edgecolor='red', alpha=0.9))
                elif '[INFO]' in alert_msg:
                    txt_obj.set_bbox(dict(boxstyle='round,pad=0.3', facecolor='#003366', edgecolor='cyan', alpha=0.9))
                else:
                    txt_obj.set_bbox(dict(boxstyle='round,pad=0.3', facecolor='#8b6508', edgecolor='yellow', alpha=0.9))
                txt_obj.set_visible(True)
            else:
                txt_obj.set_visible(False)

    def set_track(self, track_info):
        """Draw vertical corner markers on the speed axis using track metadata."""
        for artist in self._corner_artists:
            artist.remove()
        self._corner_artists.clear()

        track_length = track_info["length"]
        self.ax_speed.set_xlim(0, track_length)

        for turn in track_info["turns"]:
            name = turn["name"]
            dist = turn["distance"]
            line = self.ax_speed.axvline(x=dist, color='white', linestyle=':', alpha=0.3)
            label = self.ax_speed.text(dist + 20, 300, name, color='white', rotation=90, alpha=0.5, fontsize=8)
            self._corner_artists.append(line)
            self._corner_artists.append(label)

        self.fig.canvas.draw_idle()

    # ----------------------------------------------------------------
    # Driver change
    # ----------------------------------------------------------------
    def set_drivers(self, driver_1, global_histories):
        """Changes the tracked driver and points the data stream to the background logs."""
        self.driver_1 = driver_1

        self.c1 = DRIVER_COLORS.get(self.driver_1, "#00FFFF")

        if self.driver_1 in global_histories:
            self.data[self.driver_1] = global_histories[self.driver_1]

        self.l_spd_1.set_color(self.c1)
        self.l_thr_1.set_color(self.c1)
        self.l_brk_1.set_color(self.c1)
        self.l_gear_1.set_color(self.c1)
        self.l_rpm_1.set_color(self.c1)

        self.fig.canvas.draw_idle()

    def _on_circuit_changed(self, selected_circuit):
        """Handle circuit selection change from the combo box."""
        if selected_circuit in self.track_metadata:
            self.current_track_key = selected_circuit
            self.set_track(self.track_metadata[selected_circuit])
            self.init_radar(selected_circuit, self.track_metadata)
            self.fig.canvas.draw_idle()

    def _set_ghost_data(self, driver_key):
        """Draw ghost (reference best lap) lines for a given driver, or hide them."""
        ghost_artists = [self.l_spd_ghost, self.l_thr_ghost, self.l_brk_ghost, self.l_gear_ghost, self.l_rpm_ghost]
        if driver_key in self.ref_data and len(self.ref_data[driver_key].get('distances', [])) > 0:
            ref = self.ref_data[driver_key]
            self.l_spd_ghost.set_data(ref['distances'], ref['speeds'])
            self.l_thr_ghost.set_data(ref['distances'], ref['throttles'])
            self.l_brk_ghost.set_data(ref['distances'], ref['brakes'])
            self.l_gear_ghost.set_data(ref['distances'], ref['gears'])
            self.l_rpm_ghost.set_data(ref['distances'], ref['rpms'])
            for a in ghost_artists:
                a.set_visible(True)
        else:
            for a in ghost_artists:
                a.set_visible(False)

    def update_plots(self):
        """Redraws the physical lines on the screen using the background data logs."""
        d1 = self.driver_1

        # --- Draw ghost reference lap FIRST (behind live data) ---
        self._set_ghost_data(d1)

        def get_safe_arrays(data_dict):
            d = list(data_dict['distances'])
            s = list(data_dict['speeds'])
            thr = list(data_dict['throttles'])
            b = list(data_dict['brakes'])
            g = list(data_dict['gears'])
            r = list(data_dict['rpms'])

            min_len = min(len(d), len(s), len(thr), len(b), len(g), len(r))
            return (d[:min_len], s[:min_len],
                    thr[:min_len], b[:min_len], g[:min_len], r[:min_len])

        if d1 in self.data and self.data[d1] and len(self.data[d1]['distances']) > 0:
            d, s, thr, b, g, r = get_safe_arrays(self.data[d1])
            self.l_spd_1.set_data(d, s)
            self.l_thr_1.set_data(d, thr)
            self.l_brk_1.set_data(d, b)
            self.l_gear_1.set_data(d, g)
            self.l_rpm_1.set_data(d, r)

        self._update_weather()
        self._update_damage()
        self._update_gforce()
        self._update_tyres()
        self._update_energy()
        self._update_timing()
        self._update_dss_alerts()

        # --- DRS indicator update ---
        if self.latest_packet is not None:
            drs_open = getattr(self.latest_packet, 'drs_open', False)
            if drs_open:
                self.drs_text.set_color('lime')
                self.drs_text.set_bbox(dict(facecolor='black', edgecolor='lime', boxstyle='round,pad=0.2'))
            else:
                self.drs_text.set_color('gray')
                self.drs_text.set_bbox(dict(facecolor='black', edgecolor='gray', boxstyle='round,pad=0.2'))

        # --- CSV Black Box logging ---
        if self.latest_packet is not None:
            w_fl, w_fr, w_rl, w_rr = getattr(self.latest_packet, 'tyres_wear', [0, 0, 0, 0])
            drs_stat = 1 if getattr(self.latest_packet, 'drs_open', False) else 0
            self.csv_writer.writerow([
                time.time(),
                self.latest_packet.current_lap_time,
                self.latest_packet.speed_kmh,
                self.latest_packet.throttle_pct,
                self.latest_packet.brake_pct,
                self.latest_packet.gear,
                drs_stat,
                w_fl, w_fr, w_rl, w_rr
            ])

        self.fig.canvas.draw_idle()

    def init_radar(self, track_key, track_metadata):
        """Load radar data from disk and display the track layout.
        Clears previous radar content to prevent ghost-map overlap."""
        self.ax_radar.clear()
        self.ax_radar.set_facecolor('#1e1e1e')
        self.ax_radar.axis('off')
        self._setup_radar_artists()

        track_info = track_metadata.get(track_key, {})
        rotation_deg = track_info.get("rotation", 0)
        self.rotation_rad = math.radians(rotation_deg)
        self.flip_x = track_info.get("flip_x", False)
        self.flip_z = track_info.get("flip_z", False)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        radar_path = os.path.join(project_root, 'data', 'radars', f'{track_key}.json')

        if os.path.exists(radar_path):
            try:
                with open(radar_path, 'r') as f:
                    track_data = json.load(f)
                self.set_track_layout(track_data['x'], track_data['z'])
            except Exception as e:
                print(f"Error loading radar {radar_path}: {e}")
                self.show_empty(track_key)
        else:
            self.show_empty(track_key)

    def show_empty(self, track_name):
        """Display a placeholder message when no radar data is available for a track."""
        self.track_line.set_data([], [])
        self.empty_text.set_text(f'Track map not recorded\n"{track_name}"')
        self.ax_radar.set_xlim(0, 1)
        self.ax_radar.set_ylim(0, 1)
        self.ax_radar.set_aspect('auto')
        self.fig.canvas.draw_idle()

    @staticmethod
    def _rotate(x, z, rad):
        """Rotate a 2D point (x, z) by rad radians around the origin."""
        return x * math.cos(rad) - z * math.sin(rad), x * math.sin(rad) + z * math.cos(rad)

    def _transform(self, x, z):
        """Apply configured rotation and optional flips to a coordinate pair."""
        if self.flip_x:
            x = -x
        if self.flip_z:
            z = -z
        return self._rotate(x, z, self.rotation_rad)

    def set_track_layout(self, x_coords, z_coords):
        """Apply transformed track coordinates to the radar plot and adjust view limits."""
        if not x_coords or not z_coords:
            return

        clean_x = [x for x in x_coords if x is not None and not math.isnan(x)]
        clean_z = [z for z in z_coords if z is not None and not math.isnan(z)]

        if not clean_x or not clean_z:
            return

        transformed_x = []
        transformed_z = []
        for x, z in zip(clean_x, clean_z):
            tx, tz = self._transform(x, z)
            transformed_x.append(tx)
            transformed_z.append(tz)

        self.track_line.set_data(transformed_x, transformed_z)

        padding_x = (max(transformed_x) - min(transformed_x)) * 0.1
        padding_z = (max(transformed_z) - min(transformed_z)) * 0.1

        self.ax_radar.set_xlim(min(transformed_x) - padding_x, max(transformed_x) + padding_x)
        self.ax_radar.set_ylim(min(transformed_z) - padding_z, max(transformed_z) + padding_z)
        self.ax_radar.set_aspect('equal')

        self.fig.canvas.draw_idle()

    def update_positions(self, full_telemetry_dict):
        """Update car positions on the radar from live telemetry data."""
        player = full_telemetry_dict.get('VER')
        if not player:
            self.fig.canvas.draw_idle()
            return

        grid_x = getattr(player, 'grid_x', [])
        grid_z = getattr(player, 'grid_z', [])
        player_idx = getattr(player, 'player_car_index', 0)

        if not grid_x or not grid_z:
            self.fig.canvas.draw_idle()
            return

        player_visible = False
        n = min(len(grid_x), len(self.grid_dots))

        for i in range(n):
            x, z = grid_x[i], grid_z[i]
            if abs(x) < 0.1 and abs(z) < 0.1:
                self.grid_dots[i].set_visible(False)
                continue

            tx, tz = self._transform(x, z)

            if i == player_idx:
                self.grid_dots[i].set_visible(False)
                self.player_dot.set_visible(True)
                self.player_dot.set_data([tx], [tz])
                player_visible = True
            else:
                dot = self.grid_dots[i]
                dot.set_visible(True)
                dot.set_data([tx], [tz])
                dot.set_color('#AAAAAA')
                dot.set_markersize(5)
                dot.set_alpha(0.5)
                dot.set_zorder(8)

        for i in range(n, len(self.grid_dots)):
            self.grid_dots[i].set_visible(False)

        if not player_visible:
            self.player_dot.set_visible(False)

        self.fig.canvas.draw_idle()
