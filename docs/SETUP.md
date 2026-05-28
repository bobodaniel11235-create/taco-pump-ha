# Setup Guide

## Prerequisites

- Home Assistant OS running on Raspberry Pi
- Taco VR25H-F at 192.168.1.201 on same subnet as HA
- ESP32 dev board + MAX485 module wired to VR3452 RS-485 terminals
- Shelly EM installed on 0034e Plus circuit

---

## Step 1 — Mosquitto MQTT broker

1. Settings → Add-ons → Add-on Store → search **Mosquitto broker** → Install
2. Configuration tab — paste:
   ```yaml
   logins:
     - username: mqtt_user
       password: your_strong_password
   require_certificate: false
   ```
3. Save → Start → Enable start on boot
4. Settings → Devices & Services — accept the MQTT integration prompt
   Enter: host=localhost, port=1883, username/password from above

---

## Step 2 — AppDaemon (VR25H-F polling)

1. Settings → Add-ons → Add-on Store → search **AppDaemon** → Install
2. Configuration tab:
   ```yaml
   python_packages:
     - requests
     - beautifulsoup4
   ```
3. Save → Start → Enable start on boot
4. In File Editor, open `/config/appdaemon/appdaemon.yaml` — replace contents:
   ```yaml
   appdaemon:
     latitude: 37.3382
     longitude: -121.8863
     elevation: 82
     time_zone: America/Los_Angeles
     plugins:
       HASS:
         type: hass
         ha_url: http://supervisor/core
         token: !secret appdaemon_token
         cert_verify: false
   http:
     url: http://127.0.0.1:5050
   admin:
   api:
   hadashboard:
   ```
5. In `/config/secrets.yaml` add: `appdaemon_token: YOUR_LONG_LIVED_TOKEN`
   (Generate token: Profile → Security → Long-Lived Access Tokens)
6. Copy `appdaemon/apps/apps.yaml` → `/config/appdaemon/apps/apps.yaml`
7. Copy `appdaemon/apps/taco_pump_poller.py` → `/config/appdaemon/apps/`
8. Restart AppDaemon add-on
9. Check AppDaemon log — within 30s should see published sensor values

**Fix FIELD_MAP for your pump's exact labels:**
```python
FIELD_MAP = {
    "flow":     "flow_rate",   # matches "Flow:"
    "power":    "power",       # matches "Power:"
    "rpm":      "rpm",         # matches "RPM:"
    "motor t":  "motor_temp",  # matches "Motor T:"  ← confirmed from curl
    "head":     "head",
    "current":  "current",
    "volt":     "voltage",
}
```

---

## Step 3 — ESPHome (VR3452 RS-485)

### Hardware wiring
```
ESP32 GPIO17 (TX2) → MAX485 DI
ESP32 GPIO16 (RX2) → MAX485 RO
ESP32 GPIO4        → MAX485 DE + RE (bridge these two pins)
MAX485 A           → Pump terminal A
MAX485 B           → Pump terminal B
MAX485 GND         → Pump terminal SH / GND
MAX485 VCC         → ESP32 3.3V
```

### Firmware deployment

1. Settings → Add-ons → ESPHome → Install → Start
2. Fill in `esphome/secrets.yaml` with WiFi credentials and API key
3. Flash `esphome/vr3452_diagnostic.yaml` via web.esphome.io (USB first flash)
4. Open ESPHome dashboard → vr3452 → Logs
5. Wait 60s — look for `[I][scan] INPUT reg X = NNN` lines
6. Cross-reference non-zero values with pump web interface current readings
7. Record register addresses for head, flow, power, RPM, temperature
8. Fill addresses into `esphome/vr3452_production.yaml` (replace `0xTODO`)
9. ESPHome dashboard → Install → Wirelessly (OTA update)
10. Settings → Devices & Services → accept ESPHome device prompt

**VR3452 Modbus defaults:**
- Slave address: **245** (0xF5) — verify in pump web interface
- Baud rate: **19200**
- Parity: None, Stop bits: 1

**Unit conversions (confirmed from Taco manual):**
- Head: raw × 0.03281 = ft (stored as 0.01 m per count)
- Flow: raw × 0.4403 = GPM (stored as 0.1 m³/h per count)

---

## Step 4 — Shelly EM (0034e Plus)

1. Physical install: CT clamp around hot wire only (not both wires)
   Use 20A CT clamp (not included 50A) for better accuracy at low loads
2. Power on → connect to ShellyEM-XXXXXX WiFi AP → browse 192.168.33.1
3. Set WiFi SSID/password → device joins home network
4. Assign static IP 192.168.1.203, device name `shellyem-0034e`
5. Settings → Devices & Services → Add Integration → Shelly
6. Rename entities to match dashboard entity IDs:
   - `sensor.shellyem_0034e_power`
   - `sensor.shellyem_0034e_current`
   - `sensor.shellyem_0034e_voltage`

---

## Step 5 — Home Assistant configuration.yaml

1. Open File Editor → `/config/configuration.yaml`
2. Paste full contents of `homeassistant/taco_mqtt_sensors.yaml` at bottom
3. Paste full contents of `homeassistant/template_sensors.yaml` at bottom
   (merge under existing `template:` key if one exists — don't duplicate the key)
4. Developer Tools → YAML → Check Configuration
5. Restart HA

---

## Step 6 — Lovelace dashboard

1. Open your dashboard → ⋮ menu → Edit → Raw configuration editor
2. Replace entire contents with `homeassistant/lovelace_dashboard.yaml`
3. Save

**Before pasting:** verify entity IDs match what HA created.
Settings → Entities → search `vr25h`, `vr3452`, `shellyem` to confirm.

---

## Verification checklist

- [ ] `mosquitto_sub -h localhost -p 1883 -u mqtt_user -P password -t "taco/vr25h/#" -v`
      shows values every 30s in Terminal add-on
- [ ] Developer Tools → States → `vr25h_power` shows current numeric value
- [ ] Developer Tools → States → `vr3452_power` shows current numeric value
- [ ] Developer Tools → States → `shellyem_0034e_power` shows current numeric value
- [ ] Developer Tools → States → `total_pump_power` shows combined wattage
- [ ] Lovelace dashboard shows all three pump cards with live data
- [ ] All three `binary_sensor.*_running` entities flip on/off with pumps
