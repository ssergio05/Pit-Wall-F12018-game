"""
Standalone track recording tool for Pit Wall OS.

Listens on UDP 20777 for the F1 2018 game feed, prompts for a
track name, waits for the player to complete a full lap, and
saves the world X/Z coordinates to ``data/radars/{track_name}.json``.

Usage::

    python tools/record_track.py
"""

import socket
import struct
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UDP_IP = "0.0.0.0"
UDP_PORT = 20777

HEADER_FORMAT = '<HBBQfIB'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MOTION_CAR_SIZE = 60
LAPDATA_CAR_SIZE = 41


def main():
    """Run the track recording workflow: prompt for name, listen for UDP lap data,
    and save coordinates on lap completion."""
    track_name = input('Enter circuit name to record (e.g. monaco, spain): ')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(120.0)
    print(f" Listening on UDP {UDP_IP}:{UDP_PORT}...")

    prev_lap_distance = -1.0
    seen_high = False
    recording = False
    track_x = []
    track_z = []

    print(" Waiting for finish line crossing...")

    while True:
        try:
            data, addr = sock.recvfrom(1500)
        except socket.timeout:
            print(" Timeout: no packets received in 120s.")
            break

        if len(data) < HEADER_SIZE:
            continue

        header = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        packet_id = header[2]
        player_idx = header[6]

        if packet_id == 0:
            car_offset = HEADER_SIZE + (player_idx * MOTION_CAR_SIZE)
            if len(data) >= car_offset + 12:
                world_x, world_y, world_z = struct.unpack(
                    '<fff', data[car_offset:car_offset + 12]
                )
                if recording:
                    track_x.append(world_x)
                    track_z.append(world_z)

        elif packet_id == 2:
            car_offset = HEADER_SIZE + (player_idx * LAPDATA_CAR_SIZE)
            lap_dist_offset = car_offset + 20
            if len(data) >= lap_dist_offset + 4:
                lap_distance, = struct.unpack('<f', data[lap_dist_offset:lap_dist_offset + 4])

                if lap_distance > 100.0:
                    seen_high = True

                crossing = seen_high and lap_distance < 50.0 and prev_lap_distance > 100.0

                if crossing and not recording:
                    recording = True
                    track_x.clear()
                    track_z.clear()
                    print(" Lap started! Recording coordinates...")

                elif crossing and recording:
                    recording = False
                    print(f" Lap completed! {len(track_x)} points recorded.")

                    output_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'data', 'radars'
                    )
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f'{track_name}.json')

                    with open(output_path, 'w') as f:
                        json.dump({"x": track_x, "z": track_z}, f)
                    print(f" Saved to: {output_path}")
                    break

                prev_lap_distance = lap_distance

    sock.close()


if __name__ == '__main__':
    main()
