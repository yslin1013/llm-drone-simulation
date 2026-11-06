# Validation Results

## Recorded flight

The included video corresponds to `logs/20261103-210836/events.jsonl`.

| Measurement | Observed |
| --- | --- |
| Height | 3.007683 m |
| Forward displacement | 4.982964 m |
| Clockwise heading change | 89.5 degrees |
| Horizontal target error | 0.020946 m |
| Landing telemetry | in_air=false |

The run exercised local Ollama tool calling, parameter validation, MAVSDK takeoff and Offboard control, PX4 flight control, Gazebo physics, and landing. The log includes the model response, coordinate conversion, SDK calls, and telemetry.

## Parameter tests

Validation tests previously passed for a valid plan and rejection of string or false landing values, excessive altitude, Boolean numeric values, negative distance, NaN, and infinity. These tests do not command flight.

## Verification boundaries

- The recording is 1920 x 1080 H.264 at 30 FPS; its web-interface source was converted from 25 FPS.
- The captures are not frame-synchronized.
- The recorded environment used software rendering through WSLg.
- Subsequent logging and recovery changes received syntax and parameter checks, not a new full flight verification.
- Cloud inference, connection-loss recovery, and fault-injection behavior have not been tested end to end.
- These measurements describe one simulated run and do not establish general accuracy or reliability.
- Public-release changes are documentation and interface-label changes; no new flight run was performed for publication.
