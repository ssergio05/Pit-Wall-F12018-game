import tkinter as tk
from tkinter import filedialog
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from matplotlib.gridspec import GridSpec


class ReplayViewer:
    def __init__(self):
        root = tk.Tk()
        root.withdraw()

        csv_path = filedialog.askopenfilename(
            title='Select a CSV log file',
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')]
        )

        if not csv_path:
            print("No file selected. Exiting.")
            exit()

        self.df = pd.read_csv(csv_path)
        print(f"Loaded {len(self.df)} rows from {csv_path}")

        self._setup_figure()
        self._plot_data()
        self._setup_slider()
        self._setup_text()

        self.update(0)
        plt.show()

    def _style_axes(self, ax):
        ax.set_facecolor('#111111')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        for spine in ax.spines.values():
            spine.set_color('#555555')
        ax.grid(color='#444444', linestyle='--', alpha=0.5)

    def _setup_figure(self):
        self.fig = plt.figure(figsize=(14, 8))
        self.fig.patch.set_facecolor('#222222')

        gs = GridSpec(4, 1, figure=self.fig, hspace=0.35)
        self.fig.subplots_adjust(bottom=0.25)

        self.ax_speed = self.fig.add_subplot(gs[0, :])
        self.ax_speed.set_ylabel('Speed (km/h)')
        self.ax_speed.set_ylim(0, 360)
        self._style_axes(self.ax_speed)
        self.ax_speed.tick_params(labelbottom=False)

        self.ax_throttle = self.fig.add_subplot(gs[1, :], sharex=self.ax_speed)
        self.ax_throttle.set_ylabel('Throttle (%)')
        self.ax_throttle.set_ylim(-5, 105)
        self._style_axes(self.ax_throttle)
        self.ax_throttle.tick_params(labelbottom=False)

        self.ax_brake = self.fig.add_subplot(gs[2, :], sharex=self.ax_speed)
        self.ax_brake.set_ylabel('Brake (%)')
        self.ax_brake.set_ylim(-5, 105)
        self._style_axes(self.ax_brake)
        self.ax_brake.tick_params(labelbottom=False)

        self.ax_gear = self.fig.add_subplot(gs[3, :], sharex=self.ax_speed)
        self.ax_gear.set_ylabel('Gear')
        self.ax_gear.set_ylim(0, 9)
        self.ax_gear.set_xlabel('Sample Index')
        self._style_axes(self.ax_gear)

        self.ax_speed.margins(x=0)

        self.vlines = []
        for ax in [self.ax_speed, self.ax_throttle, self.ax_brake, self.ax_gear]:
            line = ax.axvline(x=0, color='red', linewidth=1.5, linestyle='-')
            self.vlines.append(line)

    def _plot_data(self):
        x_vals = self.df.index.values
        self.ax_speed.plot(x_vals, self.df['Speed'], color='dodgerblue', linewidth=1.5)
        self.ax_throttle.plot(x_vals, self.df['Throttle'], color='#00ff00', linewidth=1.5)
        self.ax_brake.plot(x_vals, self.df['Brake'], color='#ff0000', linewidth=1.5)
        self.ax_gear.plot(x_vals, self.df['Gear'], color='white', linewidth=1.5, drawstyle='steps-pre')

    def _setup_slider(self):
        ax_slider = self.fig.add_axes([0.1, 0.08, 0.8, 0.03])
        ax_slider.set_facecolor('#222222')
        self.time_slider = Slider(
            ax_slider, 'Time', 0, len(self.df) - 1,
            valinit=0, valfmt='%0.0f', color='dodgerblue'
        )
        self.time_slider.label.set_color('white')
        self.time_slider.on_changed(self.update)

    def _setup_text(self):
        props = dict(color='white', fontsize=14, fontfamily='monospace',
                     transform=self.fig.transFigure)
        self.speed_text = self.fig.text(0.02, 0.94, '', **props)
        self.gear_text = self.fig.text(0.02, 0.90, '', **props)

    def update(self, val):
        idx = int(self.time_slider.val)
        for line in self.vlines:
            line.set_xdata([idx, idx])
        row = self.df.iloc[idx]
        self.speed_text.set_text(f'Speed: {row["Speed"]} km/h')
        self.gear_text.set_text(f'Gear: {int(row["Gear"])}')
        self.fig.canvas.draw_idle()


if __name__ == '__main__':
    ReplayViewer()
