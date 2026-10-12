#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simple HTTP server returning system metrics as JSON on port 8888."""
import json, os, re, socket, time
from http.server import HTTPServer, BaseHTTPRequestHandler

def get_metrics():
    # CPU temperature
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            cpu_temp = int(f.read().strip()) / 1000.0
    except:
        cpu_temp = None

    # CPU load (1min average)
    try:
        with open('/proc/loadavg') as f:
            parts = f.read().split()
            load1, load5, load15 = float(parts[0]), float(parts[1]), float(parts[2])
    except:
        load1 = load5 = load15 = None

    # CPU usage % (from /proc/stat - instant snapshot)
    try:
        def read_cpu():
            with open('/proc/stat') as f:
                line = f.readline()
            vals = list(map(int, line.split()[1:]))
            idle = vals[3]
            total = sum(vals)
            return total, idle
        t1, i1 = read_cpu()
        time.sleep(0.2)
        t2, i2 = read_cpu()
        cpu_pct = round(100.0 * (1.0 - (i2-i1)/(t2-t1)), 1)
    except:
        cpu_pct = None

    # Memory
    try:
        meminfo = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':')
                meminfo[k.strip()] = int(v.split()[0])
        mem_total = meminfo.get('MemTotal', 0) // 1024
        mem_avail = meminfo.get('MemAvailable', 0) // 1024
        mem_used  = mem_total - mem_avail
        mem_pct   = round(100.0 * mem_used / mem_total, 1) if mem_total else 0
    except:
        mem_total = mem_used = mem_pct = None

    # Uptime
    try:
        with open('/proc/uptime') as f:
            uptime_s = float(f.read().split()[0])
    except:
        uptime_s = None

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = ''

    # CPU count
    try:
        cpu_count = os.cpu_count()
    except:
        cpu_count = 4

    return {
        'cpu_temp':  cpu_temp,
        'cpu_pct':   cpu_pct,
        'load1':     load1,
        'load5':     load5,
        'load15':    load15,
        'cpu_count': cpu_count,
        'mem_total': mem_total,
        'mem_used':  mem_used,
        'mem_pct':   mem_pct,
        'uptime_s':  uptime_s,
        'ts':        time.time(),
        # Lets the GCS label drones found by subnet scan (not via Bonjour).
        'hostname':  hostname,
        'name':      display_name(hostname),
    }

def display_name(hostname):
    """bumblebee-20ec -> Bumblebee-20EC (as in the Bonjour record and the
    hotspot SSID); any other hostname just gets a capital first letter."""
    if re.fullmatch(r'bumblebee-[0-9a-f]{4}', hostname):
        return 'Bumblebee-' + hostname[-4:].upper()
    return hostname[:1].upper() + hostname[1:]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(get_metrics()).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass  # suppress logs

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8888), Handler)
    print('Metrics server on :8888')
    server.serve_forever()
