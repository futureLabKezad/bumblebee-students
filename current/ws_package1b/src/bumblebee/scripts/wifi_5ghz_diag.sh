#!/bin/bash
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

# Diagnose 5 GHz scan capability on this drone (nmcli + sysfs only, no iw dep).
set -u

echo "== chipset =="
grep -E 'DRIVER|SDIO_ID|MODALIAS' /sys/class/ieee80211/phy0/device/uevent 2>/dev/null \
  || echo "phy0 not present"

echo
echo "== regulatory domain =="
echo -n "cfg80211.ieee80211_regdom = "
cat /sys/module/cfg80211/parameters/ieee80211_regdom 2>/dev/null
grep -oE 'cfg80211\.ieee80211_regdom=[A-Z]{2}' /boot/firmware/cmdline.txt 2>/dev/null \
  | head -1 || echo "cmdline.txt: no regdom override"

echo
echo "== iw tool =="
if command -v iw >/dev/null 2>&1; then
  iw reg get | head -10
  echo "-- 5 GHz channels in driver capability (phy0 Band 2):"
  iw list 2>/dev/null | sed -n '/Band 2/,/Band 3/p' | grep -E 'MHz|disabled|no IR|radar' | head -40
  echo "-- direct active 5 GHz scan (UNII-1/2/3):"
  sudo iw dev wlan0 scan freq 5180 5200 5220 5240 5260 5280 5300 5320 \
    5500 5520 5540 5560 5580 5600 5620 5640 5660 5680 5700 \
    5745 5765 5785 5805 5825 2>&1 \
    | awk '/^BSS/{bss=$2} /freq:/{f=$2} /SSID:/{print bss"  "f" MHz  "$0}' | head -40
else
  echo "iw not installed (run: sudo apt-get install -y iw). Skipping iw-based probes."
fi

echo
echo "== nmcli rescan + grouped by band =="
nmcli dev wifi rescan 2>/dev/null
sleep 2
nmcli -t -f SSID,FREQ,SIGNAL,SECURITY dev wifi list 2>/dev/null | \
  awk -F: 'BEGIN{c24=0; c5=0; c6=0}
    {
      ssid=$1; freq=$2+0; sig=$3; sec=$4;
      if (ssid=="") next;
      band = (freq<3000)?"2.4G":(freq<5900?"5G":"6G");
      if (band=="2.4G") c24++; else if (band=="5G") c5++; else c6++;
      printf "  %-4s %5d MHz  %3s%%  %-12s  %s\n", band, freq, sig, sec, ssid;
    }
    END {
      print "";
      print "  totals: 2.4G="c24"  5G="c5"  6G="c6;
    }'

echo
echo "== current connection =="
nmcli -t -f DEVICE,STATE,CONNECTION device status | grep '^wlan0:'
nmcli -f IN-USE,SSID,FREQ,SIGNAL dev wifi list 2>/dev/null | grep '^\*' | head -1

echo
echo "Tip: iPhone Personal Hotspot defaults to 2.4 GHz with 'Maximize"
echo "Compatibility' ON. Toggle it OFF in iPhone Settings to broadcast on"
echo "5 GHz, then re-run this script to confirm 5G visibility."
