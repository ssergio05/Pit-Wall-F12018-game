import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import math

class LiveTrackMap(ctk.CTkToplevel):
    """
    Pop-up radar window showing the full 20-car grid positions on a
    transformed track map.

    Args:
        master: Parent CTk widget.
        d1: Three-letter driver code for the player car.
        rotation_deg: Track rotation in degrees (from track metadata).
        flip_x: Whether to mirror the X axis.
        flip_z: Whether to mirror the Z axis.
    """
    def __init__(self, master, d1="VER", rotation_deg=0, flip_x=False, flip_z=False, **kwargs):
        super().__init__(master, **kwargs)

        self.title("Pit Wall OS - Full Grid Radar")
        self.geometry("600x600")
        self.attributes('-topmost', True)

        self.d1 = d1
        self.rotation_rad = math.radians(rotation_deg)
        self.flip_x = flip_x
        self.flip_z = flip_z

        self.fig = Figure(figsize=(6, 6), facecolor='#1e1e1e')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e1e')
        self.ax.axis('off')

        self.track_line, = self.ax.plot([], [], color='#444444', linewidth=3, zorder=1)

        self.player_dot, = self.ax.plot([], [], 'o', color='#FF4444', markersize=16,
                                        markeredgecolor='white', markeredgewidth=1.5, zorder=15)

        self.grid_dots = []
        for _ in range(20):
            dot, = self.ax.plot([], [], 'o', color='#AAAAAA', markersize=5, alpha=0.5, zorder=8, visible=False)
            self.grid_dots.append(dot)

        self.empty_text = self.ax.text(
            0.5, 0.5, '', color='#666666', fontsize=18,
            ha='center', va='center', transform=self.ax.transAxes
        )

        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def show_empty(self, track_name):
        """Display a placeholder message when no radar data is available for a track."""
        self.track_line.set_data([], [])
        self.empty_text.set_text(f'Track map not recorded\n"{track_name}"')
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.ax.set_aspect('auto')
        self.canvas.draw_idle()

    @staticmethod
    def _rotate(x, z, rad):
        """Rotate a 2D point (x, z) by rad radians around the origin."""
        return x * math.cos(rad) - z * math.sin(rad), x * math.sin(rad) + z * math.cos(rad)

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

        self.ax.set_xlim(min(transformed_x) - padding_x, max(transformed_x) + padding_x)
        self.ax.set_ylim(min(transformed_z) - padding_z, max(transformed_z) + padding_z)

        self.ax.set_aspect('equal')

        self.canvas.draw_idle()

    def _transform(self, x, z):
        """Apply configured rotation and optional flips to a coordinate pair."""
        if self.flip_x:
            x = -x
        if self.flip_z:
            z = -z
        return self._rotate(x, z, self.rotation_rad)

    def update_positions(self, full_telemetry_dict):
        player = full_telemetry_dict.get('VER')
        if not player:
            self.canvas.draw_idle()
            return

        grid_x = getattr(player, 'grid_x', [])
        grid_z = getattr(player, 'grid_z', [])
        player_idx = getattr(player, 'player_car_index', 0)

        if not grid_x or not grid_z:
            self.canvas.draw_idle()
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

        self.canvas.draw_idle()