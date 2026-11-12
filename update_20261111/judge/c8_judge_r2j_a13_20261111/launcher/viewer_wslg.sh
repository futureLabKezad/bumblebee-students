#!/bin/bash
# viewer_wslg.sh SIDE_DIR RENDER GPU_ENV [PARENT_PID] - Gazebo window on WSLg (DISPLAY=:0) for a trial run. SIMULATOR ONLY.
# Ends when SIDE_DIR/stop exists or when PARENT_PID (the launcher) is gone, so an interrupted launcher leaves no viewer.
# Same logic as viewer_helper in pc_handover_20261017/setup/gpu_and_parity_check.sh (reviewed 17.10):
# follows the trial server (/work/sim/run/gz.pid with GZ_PARTITION=bbtrial), copies its gz-transport settings,
# starts `gz sim -g` with setsid and records ITS OWN process group; while /work/sim/run/MEASURING exists the window
# stays closed (only that group is stopped). Never pkill -f. Ends when SIDE_DIR/stop exists.
set -u
SIDE=${1:?side dir}; RENDER=${2:-hr1}; GPU_ENV=${3:?gpu_env.sh}; PARENT=${4:-}
CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
OGRE_LOGS=("$HOME/.gz/rendering/ogre2.log" "$HOME/.gz/ogre2.log")
ogre_log() { local f best="" bt=0 t; for f in "${OGRE_LOGS[@]}"; do [ -f "$f" ] || continue; t=$(stat -c %Y "$f"); [ "$t" -gt "$bt" ] && { bt=$t; best=$f; }; done; echo "$best"; }
stop_group() { local g=$1; [ -n "$g" ] || return 0; kill -INT -- "-$g" 2>/dev/null; sleep 2; kill -TERM -- "-$g" 2>/dev/null; sleep 1; kill -KILL -- "-$g" 2>/dev/null; return 0; }
GUI_VARS=(DISPLAY=:0 QT_QPA_PLATFORM=xcb)
if [ "$RENDER" = sw ]; then GUI_VARS+=(LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe)
else while read -r v; do [ -n "$v" ] && GUI_VARS+=("$v"); done < <(sed -n 's/^export \([A-Za-z_][A-Za-z0-9_]*=[^ ]*\)$/\1/p' "$GPU_ENV"); fi
[ -n "${XDG_RUNTIME_DIR:-}" ] && GUI_VARS+=("XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")
last=""; gpid=""; gui_started=0; copied_gui=0
while [ ! -e "$SIDE/stop" ]; do
  if [ -n "$PARENT" ] && ! kill -0 "$PARENT" 2>/dev/null; then echo "$(date +%T) launcher $PARENT gone: stopping" >> "$SIDE/viewer.log"; break; fi
  if [ -e /work/sim/run/MEASURING ]; then
    if [ -n "$gpid" ]; then stop_group "$gpid"; echo "$(date +%T) MEASURING: GUI group $gpid closed" >> "$SIDE/viewer.log"; gpid=""; fi
    sleep 1; continue
  fi
  srv="$(cat /work/sim/run/gz.pid 2>/dev/null || true)"
  if [ -n "$srv" ] && [ "$srv" != "$last" ] && tr '\0' '\n' < "/proc/$srv/environ" 2>/dev/null | grep -qx 'GZ_PARTITION=bbtrial'; then
    last=$srv; t0=$(date +%s)
    echo "$(date +%T) server $srv found" >> "$SIDE/viewer.log"
    tr '\0' '\n' < "/proc/$srv/environ" 2>/dev/null \
      | grep -E '^(HR|DISPLAY|QT_QPA_PLATFORM|LIBGL_ALWAYS_SOFTWARE|GALLIUM_DRIVER|LP_NUM_THREADS|MESA_[A-Z0-9_]+|GZ_PARTITION|GZ_IP)=' \
      > "$SIDE/server_env.txt" || true
    for i in $(seq 40); do
      ol="$(ogre_log)"
      if [ -n "$ol" ] && [ "$(stat -c %Y "$ol")" -ge "$t0" ] && grep -q 'GL_RENDERER\|RenderSystem' "$ol"; then break; fi
      sleep 1
    done
    ol="$(ogre_log)"; [ -n "$ol" ] && [ "$(stat -c %Y "$ol")" -ge "$t0" ] && cp "$ol" "$SIDE/ogre2_server.log"
    mapfile -t envs < <(tr '\0' '\n' < "/proc/$srv/environ" | grep -E '^GZ_(PARTITION|IP|SIM_RESOURCE_PATH|SIM_SYSTEM_PLUGIN_PATH)=')
    setsid env -i "HOME=$HOME" "USER=$USER" "PATH=$CLEAN_PATH" LANG=C.UTF-8 "${envs[@]}" "${GUI_VARS[@]}" gz sim -g \
      > "$SIDE/gui.log" 2>&1 < /dev/null &
    gpid=$!; gui_started=$(date +%s); copied_gui=0
    echo "$(date +%T) GUI started, group $gpid, env: ${GUI_VARS[*]}" >> "$SIDE/viewer.log"
  fi
  if [ -n "$gpid" ] && [ "$copied_gui" = 0 ] && [ $(( $(date +%s) - gui_started )) -ge 20 ]; then
    ol="$(ogre_log)"; [ -n "$ol" ] && cp "$ol" "$SIDE/ogre2_gui.log"; copied_gui=1
  fi
  sleep 1
done
[ -n "$gpid" ] && stop_group "$gpid"
exit 0
