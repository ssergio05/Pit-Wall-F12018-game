import sys

from core.strategy_engine import StrategyEngine
from adapters.in_f1_2018 import F12018Adapter
from ui.main_window import PitWallDashboard

def main():
    """Application entry point. Initialises the strategy engine, UDP adapter,
    and UI dashboard, then enters the CTk main loop."""
    print("Booting Pit Wall OS...")

    strategy_engine = StrategyEngine()
    telemetry_adapter = F12018Adapter(host='0.0.0.0', port=20777)

    dashboard = PitWallDashboard()

    try:
        telemetry_adapter.start()

        print("Launching UI Dashboard...")
        dashboard.mainloop()

    except KeyboardInterrupt:
        print("\nForce quit detected.")
    finally:
        print("Cleaning up background processes...")
        telemetry_adapter.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()