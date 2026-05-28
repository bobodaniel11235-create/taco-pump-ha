# taco-pump-ha

Home Assistant integration for Taco 00e series hydronic pumps.
Monitors VR25H-F, VR3452, and 0034e Plus via WiFi with live sensor
data in a Lovelace dashboard.

## Architecture

```
VR25H-F ─── Ethernet ──► AppDaemon (HTTP poll /tbl.htm)
VR3452  ─── RS-485 ────► ESP32 + MAX485 (ESPHome Modbus RTU)
0034e Plus ─ CT clamp ──► Shelly EM
                              │
                    All three ▼
                       Mosquitto MQTT broker
                              │
                              ▼
                    Home Assistant core
                              │
                              ▼
                    Lovelace pump dashboard
```

## Pumps

| Pump | Integration | Status |
|------|-------------|--------|
| VR25H-F | AppDaemon → MQTT | IP: 192.168.1.201 |
| VR3452 | ESP32 ESPHome (Modbus RTU RS-485) | Modbus addr: 245, baud: 19200 |
| 0034e Plus | Shelly EM | Power monitoring only |

## Repository structure

```
taco-pump-ha/
├── appdaemon/
│   └── apps/
│       ├── apps.yaml              # AppDaemon app registration
│       └── taco_pump_poller.py    # VR25H-F HTTP poller → MQTT
├── esphome/
│   ├── secrets.yaml               # YOUR SECRETS — never commit this
│   ├── vr3452_diagnostic.yaml     # Deploy first — scans registers
│   └── vr3452_production.yaml     # Deploy after register scan
├── homeassistant/
│   ├── taco_mqtt_sensors.yaml     # Paste into configuration.yaml
│   ├── template_sensors.yaml      # Paste into configuration.yaml
│   └── lovelace_dashboard.yaml    # Paste into raw Lovelace editor
├── docs/
│   └── SETUP.md                   # Step-by-step setup order
├── .gitignore
└── README.md
```

## Setup order

1. Install Mosquitto broker add-on, configure credentials
2. Install AppDaemon add-on, copy `appdaemon/apps/` files
3. Flash `esphome/vr3452_diagnostic.yaml` to ESP32, confirm Modbus comms
4. Fill register addresses in `esphome/vr3452_production.yaml`, OTA update
5. Install Shelly EM, add Shelly integration to HA
6. Paste `homeassistant/taco_mqtt_sensors.yaml` and `template_sensors.yaml`
   into `configuration.yaml`, restart HA
7. Paste `homeassistant/lovelace_dashboard.yaml` into Lovelace raw editor

## MQTT topics (VR25H-F)

```
taco/vr25h/power          W
taco/vr25h/flow_rate      GPM
taco/vr25h/rpm            RPM
taco/vr25h/motor_temp     °F
taco/vr25h/head           ft
taco/vr25h/running        true | false
taco/vr25h/availability   online | offline
```

## Key settings

- VR25H-F IP: `192.168.1.201`
- VR3452 Modbus default address: `245` (0xF5)
- VR3452 baud rate default: `19200`
- Poll interval: `30s`
- Running threshold (power-derived): `> 5W`

## Known issues / TODO

- [ ] Fill `0xTODO` register addresses in `vr3452_production.yaml`
      after running the diagnostic scan
- [ ] Confirm VR3452 Modbus address in pump web interface
      (may differ if changed from factory default)
- [ ] Assign static IP to ESP32 in `vr3452_production.yaml`
