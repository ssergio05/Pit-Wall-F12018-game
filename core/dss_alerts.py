from core.models import TelemetryPacket


def evaluate_dss_alerts(packet: TelemetryPacket) -> list[str]:
    """Evaluate a telemetry packet against alert thresholds and return a list of warning strings.

    Checks include: high tyre wear (>50%), brake overheating (>1000°C),
    pit status, flag status (blue/yellow/red), and aero damage severity.

    Args:
        packet: The incoming TelemetryPacket to evaluate.

    Returns:
        A list of human-readable alert strings, e.g. "[WARNING] High Tyre Degradation (>50%)".
    """
    alerts = []

    wear = getattr(packet, 'tyres_wear', [])
    if wear and max(wear) > 50:
        alerts.append("[WARNING] High Tyre Degradation (>50%) - Consider Pit Stop")

    brakes = getattr(packet, 'brakes_temp', [])
    if brakes and any(t > 1000 for t in brakes):
        alerts.append("[CRITICAL] Brake Overheating - Lift and Coast")

    if hasattr(packet, 'pit_status') and packet.pit_status > 0:
        alerts.append("[INFO] Pit Lane Limiter Engaged")

    fia_flag = getattr(packet, 'fia_flag', 0)
    if fia_flag == 2:
        alerts.append("[INFO] BLUE FLAG - Let faster cars pass")
    elif fia_flag == 3:
        alerts.append("[WARNING] YELLOW FLAG - No overtaking")
    elif fia_flag == 4:
        alerts.append("[CRITICAL] RED FLAG - Session Suspended")

    aero = getattr(packet, 'aero_damage', None)
    if aero:
        fl, fr, rw = aero
        if fl > 20 or fr > 20 or rw > 20:
            alerts.append("[CRITICAL] Severe Aero Damage Detected")
        elif fl > 0 or fr > 0 or rw > 0:
            alerts.append("[WARNING] Minor Aero Damage")

    return alerts
