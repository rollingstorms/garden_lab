# Pico Moisture Firmware

This folder is a placeholder for the Pico W moisture probe firmware.

Target behavior:

- read a moisture probe locally
- normalize the reading to the shared platform schema
- POST the reading to `POST /api/ingest/sensors/{sensor_id}`
- authenticate with a per-device token
- retry and sleep efficiently
