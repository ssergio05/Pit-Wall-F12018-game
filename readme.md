# 🏎️ Pit Wall OS - F1 Live Telemetry Dashboard

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Matplotlib](https://img.shields.io/badge/Matplotlib-Data_Vis-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

Pit Wall OS is a professional-grade, real-time telemetry dashboard designed for F1 simulation games (specifically built around the F1 2018 UDP telemetry format). It transforms raw UDP packet data into actionable engineering insights, replicating the environment of a real Formula 1 pit wall.

## ✨ Key Features

* **📡 Real-Time Data Acquisition:** Zero-latency parsing of F1 UDP packets (Motion, Session, Car Telemetry, Car Status).
* **📈 Live Telemetry Scrubbing:** Dynamic rendering of Speed, Throttle, Brake, and Gear traces using Matplotlib in Dark Mode.
* **🛡️ Car Survival Monitor:** Live tracking of tyre wear, tyre temperatures (surface & inner core), brake temperatures, and aerodynamic structural damage.
* **🗺️ Dynamic Track Mapping:** Real-time 3D-to-2D GPS mapping using pre-recorded track metadata for instant track rendering.
* **🚨 DSS (Dynamic Strategy System):** Intelligent pop-up alerts for yellow/red flags, critical aero damage, and pit lane limiter status.
* **💾 Black Box Data Logger:** Background continuous CSV logging of all telemetry metrics for post-session analysis.
* **🎬 Replay Viewer:** Dedicated secondary module to load and scrub through previous session CSVs with a timeline slider.

## 🛠️ Architecture

The application is built on a custom lightweight architecture avoiding heavy game engines, focusing purely on data visualization:
* **Backend:** Python struct unpacking for raw UDP sockets.
* **Frontend:** `Tkinter` for window management and `Matplotlib` for high-frequency canvas rendering.
* **Data Processing:** Asynchronous packet evaluation and state machine management.

## 🚀 Installation & Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/ssergio05/Pit-Wall-F12018-game.git
   cd Pit-Wall-F12018-game
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure the Game: Go to your F1 game settings -> Telemetry Settings. Enable UDP Telemetry and set the port to `20777` (default).

4. Run the Dashboard:
   ```bash
   python main.py
   ```

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License
This project is licensed under the MIT License - see the LICENSE file for details.
