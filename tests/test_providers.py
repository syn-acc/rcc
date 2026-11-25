"""Exercise RCC's public CLI with local transports. No provider account or compute required."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest


RCC = Path(__file__).resolve().parents[1] / "rcc"


class Providers(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(dir="/tmp")))
        self.socket = str(self.root / "legs.sock")
        self.config = self.root / "profiles.json"
        self.params = self.root / "experiment.json"
        self.params.write_text('{"seed":7}')
        self.config.write_text('{"providers":{}}')

    def cli(self, *args, ok=True):
        proc = subprocess.run([str(RCC), "--config", str(self.config), "--socket", self.socket, *args],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0 if ok else 1, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def test_colab_ids_and_dry_wire_remain_compatible(self):
        requests = []
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(self.socket)
        server.listen()
        server.settimeout(5)

        def respond():
            replies = [{"ok": True, "dry": True}, {"ok": True, "stride": {"id": "original", "kind": "colab"}}]
            for reply in replies:
                conn, _ = server.accept()
                with conn, conn.makefile("rb") as stream:
                    requests.append(json.load(stream))
                    conn.sendall(json.dumps(reply).encode())

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        self.assertTrue(self.cli("plan", "--provider", "colab", "--params", str(self.params))["dry"])
        self.assertEqual(self.cli("result", "original")["stride"]["id"], "original")
        thread.join(5)
        self.assertEqual(requests, [{"action": "stride", "kind": "colab", "params": {"seed": 7}, "dry": True},
                                    {"action": "result", "id": "original"}])

    def test_profile_ids_recovery_and_fail_closed_eligibility(self):
        driver = self.root / "driver"
        calls = self.root / "calls"
        driver.write_text('''#!/usr/bin/env python3
import sys, json
r = json.load(sys.stdin)
with open(r["config"]["log"], "a") as f: print(json.dumps(r), file=f)
if r.get("config", {}).get("lose") and r["action"] == "run": sys.exit(1)
if r["action"] == "status":
    body = {"description": {"workload": "managed-job"}}
else:
    body = {"stride": {"id": r.get("id", "same"), "status": "done"}}
print(json.dumps({"ok": True, **body}))
''')
        os.chmod(driver, 0o755)
        profiles = {name: {"driver": str(driver), "config": {"log": str(calls)}} for name in ("one", "two")}
        profiles["two"].update(resident=True)
        profiles["two"]["config"]["lose"] = True
        self.config.write_text(json.dumps({"providers": profiles}))
        self.assertIn("one", self.cli("providers")["profiles"])
        self.assertFalse(calls.exists())
        job = self.cli("run", "--provider", "one", "--params", str(self.params))
        self.assertEqual(job["stride"]["id"], "one:same")
        self.assertEqual(self.cli("result", "one:same")["stride"]["id"], "one:same")
        self.assertTrue(self.cli("run", "--provider", "two", "--params", str(self.params), ok=False)["ambiguous"])
        status = self.cli("status", ok=False)
        self.assertNotIn("two", status["kinds"])
        self.assertIn("two", status["provider_errors"])
        self.assertEqual([json.loads(r)["action"] for r in calls.read_text().splitlines()],
                         ["run", "result", "run", "status"])

    def test_node_disconnect_and_lost_submit_receipt(self):
        self.config.write_text(json.dumps({"providers": {
            "bench": {"driver": "rccd", "config": {"socket": self.socket}},
            "away": {"driver": "rccd", "config": {"socket": str(self.root / "offline")}},
        }}))
        requests = []
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(self.socket)
            server.listen()
            server.settimeout(5)

            def worker():
                for reply in ({"ok": True, "description": {"workload": "container-job"}}, None):
                    peer, _ = server.accept()
                    with peer, peer.makefile("rb") as stream:
                        requests.append(json.load(stream))
                        if reply:
                            peer.sendall(json.dumps(reply).encode())

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            nodes = self.cli("nodes", ok=False)["nodes"]
            self.assertTrue(nodes["bench"]["online"])
            self.assertFalse(nodes["away"]["online"])
            lost = self.cli("run", "--provider", "bench", "--params", str(self.params), ok=False)
            self.assertTrue(lost["ambiguous"])
            thread.join(5)
            self.assertEqual(requests, [{"protocol": 1, "action": "status"},
                                        {"protocol": 1, "action": "run", "params": {"seed": 7}}])
