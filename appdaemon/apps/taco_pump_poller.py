"""
taco_pump_poller.py
-------------------
AppDaemon app that polls a Taco VR25H-F (or any 00e-series pump)
web interface at /tbl.htm and publishes parsed sensor values to MQTT.

File location on HA filesystem:  /config/appdaemon/apps/taco_pump_poller.py

apps.yaml entry (in /config/appdaemon/apps/apps.yaml):

  taco_vr25h_poller:
    module: taco_pump_poller
    class: TacoPumpPoller
    pump_ip: "192.168.1.201"
    pump_id: "vr25h"
    poll_interval_s: 30
    debug: false          # set true to dump raw HTML to AppDaemon log

MQTT topics published (replace "vr25h" with your pump_id if different):

  taco/vr25h/power          W       (float)
  taco/vr25h/flow_rate      GPM     (float)
  taco/vr25h/rpm                    (int)
  taco/vr25h/motor_temp     °F      (float)
  taco/vr25h/head           ft      (float)
  taco/vr25h/current        A       (float, if present)
  taco/vr25h/voltage        V       (float, if present)
  taco/vr25h/running                "true" | "false"  (derived, power > 5 W)
  taco/vr25h/availability           "online" | "offline"   (retained)

All non-availability topics are published with retain=True so HA always
has the last known value after a restart.
"""

import hassapi as hass
import requests
import re
from bs4 import BeautifulSoup


# ── Field keyword mapping ──────────────────────────────────────────────────────
#
# Taco's /tbl.htm HTML varies slightly across firmware versions. This table maps
# substrings that appear in the left-column label text → your MQTT key name.
#
# Run step 1 of the setup (curl + debug: true) to see what labels YOUR pump
# actually uses, then add or adjust entries below if anything doesn't parse.

FIELD_MAP = {
    "flow":        "flow_rate",
    "gal":         "flow_rate",   # some versions show "Gallons/Min"
    "head":        "head",
    "power":       "power",
    "watt":        "power",       # "Watts" or "Power Consumption"
    "rpm":         "rpm",
    "speed":       "rpm",         # "Motor Speed"
    "temp":        "motor_temp",
    "current":     "current",
    "amp":         "current",
    "volt":        "voltage",
}


class TacoPumpPoller(hass.Hass):

    def initialize(self):
        self.pump_ip  = self.args.get("pump_ip", "192.168.1.201")
        self.pump_id  = self.args.get("pump_id", "vr25h")
        self.interval = int(self.args.get("poll_interval_s", 30))
        self.debug    = bool(self.args.get("debug", False))
        self.root     = f"taco/{self.pump_id}"
        self.url      = f"http://{self.pump_ip}/tbl.htm"
        self._first_run = True

        self.run_every(self._poll, "now+2", self.interval)
        self.log(f"[Taco] Poller initialized → {self.url}  interval={self.interval}s")

    # ── Polling ────────────────────────────────────────────────────────────────

    def _poll(self, kwargs):
        try:
            resp = requests.get(self.url, timeout=5)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            self.log(f"[Taco] Connection refused to {self.url}: {e}", level="WARNING")
            self._pub_availability("offline")
            return
        except requests.exceptions.Timeout:
            self.log(f"[Taco] Timeout connecting to {self.url}", level="WARNING")
            self._pub_availability("offline")
            return
        except requests.exceptions.HTTPError as e:
            self.log(f"[Taco] HTTP error from {self.url}: {e}", level="ERROR")
            self._pub_availability("offline")
            return
        except Exception as e:
            self.log(f"[Taco] Unexpected error polling {self.url}: {e}", level="ERROR")
            self._pub_availability("offline")
            return

        # On first successful contact, always log the raw HTML regardless of
        # debug flag. This is your reference to verify parsing is working.
        if self._first_run:
            self.log(f"[Taco] First successful response from {self.url}:\n{resp.text[:1500]}")
            self._first_run = False

        if self.debug:
            self.log(f"[Taco] Raw HTML:\n{resp.text}", level="DEBUG")

        data = self._parse(resp.text)

        if not data:
            self.log(
                "[Taco] Parser returned no fields. The HTML table structure may not "
                "match FIELD_MAP. Enable debug:true in apps.yaml and check the raw "
                "HTML logged above, then adjust FIELD_MAP in taco_pump_poller.py.",
                level="WARNING"
            )
            return

        for key, val in data.items():
            self._pub(f"{self.root}/{key}", val)

        self._pub_availability("online")
        self.log(f"[Taco] Published: {data}", level="DEBUG")

    # ── HTML parser ───────────────────────────────────────────────────────────

    def _parse(self, html):
        """
        Parse /tbl.htm and return a dict of field_name → numeric_string.

        Strategy: scan all <tr> rows, look for a label cell and a value cell.
        Extract the first numeric sequence from the value cell.
        Match labels against FIELD_MAP using substring search.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            self.log(f"[Taco] BeautifulSoup parse error: {e}", level="ERROR")
            return {}

        data = {}
        rows = soup.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            label_text = cells[0].get_text(strip=True).lower()
            value_text = cells[-1].get_text(strip=True)   # last cell carries the value

            # Pull out the first number (int or decimal, optional leading sign)
            num = re.search(r"[-+]?\d+\.?\d*", value_text)
            if num is None:
                continue
            val_str = num.group()

            # Match label to a known field
            for keyword, field_name in FIELD_MAP.items():
                if keyword in label_text and field_name not in data:
                    data[field_name] = val_str
                    break

        # Derive running status from power (avoids needing a dedicated status register)
        if "power" in data:
            try:
                data["running"] = "true" if float(data["power"]) > 5.0 else "false"
            except ValueError:
                pass

        return data

    # ── MQTT helpers ─────────────────────────────────────────────────────────

    def _pub(self, topic, payload, retain=True, qos=1):
        """Publish via HA's mqtt.publish service (no direct broker connection needed)."""
        try:
            self.call_service(
                "mqtt/publish",
                topic=topic,
                payload=str(payload),
                retain=retain,
                qos=qos,
            )
        except Exception as e:
            self.log(f"[Taco] MQTT publish failed  topic={topic}: {e}", level="ERROR")

    def _pub_availability(self, state):
        self._pub(f"{self.root}/availability", state, retain=True)
