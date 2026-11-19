#!/bin/bash
# rc3 sessions only: plan 7.4 «Проверка "что запущено"» with ONE change — which MAVROS is expected.
# Claude, 30.10.2026; v2 02.11.2026 (PLAN_DELTA_rc3_mavros_proposal.md). Everything else is plan 7.4 (redaction 10) as is:
# BD/hostname/STEP checks, mavros_libs_<STEP>.txt (never overwritten), one mavros_node, sums vs 7.1 of this session,
# dpkg version of ros-jazzy-mavros, ros2 pkg prefix, vpe_fix.py path and count, setpoint_freshness count.
# v2 (02.11): with bp02 MAVROS the bp02 CPU criterion of redaction 9 (У1, Appendix Б) applies again at STEP=UM:
# CPU of mavros_node over 30 s not above 50% of one core and not above 2 x apt (baseline $BD/mavros_cpu_apt.txt from
# m6_cpu_apt.sh in 7.1). Stricter than v1 (30.10: record only). Other steps: record only, as v1.
# r2 02.11.2026 (review of 02.11; old text: m5_check74_rc3.sh.r1): the M3 prints file MAVROS_ARM64_SHA256SUMS.txt is
# trusted only if its sha256 = the 'MSF_SHA256=' line that M3 printed (env RC3M_MSF_SHA256, from the session log on the
# PC); no value or another sha -> stop. Comments corrected: the rollback branch is plan 7.4 PLUS one stricter check.
#
# | STEP                               | MAVROS expected (the only change)                               | package   |
# | UM, U3, T0, kill1.., (+ _2 suffix) | mavros_node + libmavros.so + libmavros_plugins.so from           | port      |
# |                                    | /home/lb/bench_ws/mavros/install (sums = M3 prints, whose own   |           |
# |                                    | sha256 = RC3M_MSF_SHA256); from /opt only libmavconn,           |           |
# |                                    | libmavros_extras_plugins, 4 mavros_msgs libs (sums = 7.1 of     |           |
# |                                    | this session and part 0a); 2 from bench_ws, 6 from /opt;        |           |
# |                                    | no libmavros*.so from /opt                                      |           |
# | rollback (+ _2)                    | apt 2.14 from /opt as plan 7.4 (0 from bench_ws), plus one      | release   |
# |                                    | check stricter than the plan: every MAVROS library is from /opt |           |
# |                                    | or bench_ws (NOPT + NBW = all)                                  |           |
# | U2                                 | not here: plan 7.4 block (MAVROS apt) — in rc3 sessions U2 and  |           |
# |                                    | УМ go before one reboot, the first check is STEP=UM             |           |
#
# Usage on the drone: BD=~/bench_<session> STEP=UM RC3M_MSF_SHA256=<MSF_SHA256 from M3> bash m5_check74_rc3.sh
#   -> last lines '7.4 ГОТОВО …', RC3M_M5_OK. RC3M_MSF_SHA256 is needed for every STEP except rollback.
# Tests on the PC: RC3M_SOURCE_ONLY=1 source this file, then call rc3m_eval / rc3m_cpu_eval with synthetic inputs
# (tests/test_m5.sh).
MW=/home/lb/bench_ws/mavros
MSF_DEFAULT=/home/lb/bench_ws/MAVROS_ARM64_SHA256SUMS.txt

rc3m_eval() {  # STEP EXE F(sha256  path of each loaded MAVROS lib) BEFORE(00_before.txt) MSF(M3 prints) MV(dpkg) V(pgrep -af vpe_fix) NV NSF EXESUM MSFSHA(M3 printed)
  local STEP="$1" EXE="$2" F="$3" BEF="$4" MSF="$5" MV="$6" V="$7" NV="$8" NSF="$9" EXESUM="${10}" MSFSHA="${11}"
  local M NOPT NBW NALL s f n p          # B, MLAB: для итоговой строки
  case "$STEP" in
    UM|UM_*|U3|U3_*|T0|T0_*|kill[0-9]*) B=port;    M=bench ;;
    rollback|rollback_*)               B=release; M=apt ;;
    U2|U2_*) echo "СТОП: STEP=$STEP проверяет блок 7.4 плана (MAVROS apt); этот блок — после УМ"; return 1 ;;
    *) echo "СТОП: неизвестный STEP=$STEP"; return 1 ;;
  esac
  NOPT=$(grep -c '  /opt/ros/jazzy/' "$F" || true)
  NBW=$(grep -c '  /home/lb/bench_ws/' "$F" || true)
  NALL=$(grep -c . "$F" || true)
  echo "библиотек MAVROS: из /opt/ros/jazzy $NOPT, из bench_ws $NBW (всего $NALL)"
  if [ $((NOPT + NBW)) != "$NALL" ]; then echo 'СТОП: есть библиотека MAVROS не из /opt/ros/jazzy и не из bench_ws'; return 1; fi
  if [ "$M" = bench ]; then
    if ! printf '%s' "$MSFSHA" | grep -qxE '[0-9a-f]{64}'; then echo "СТОП: нет sha256 отпечатков M3 (RC3M_MSF_SHA256 = строка MSF_SHA256= из вывода M3 этой сессии)"; return 1; fi
    if [ "$(sha256sum < "$MSF" | cut -d' ' -f1)" != "$MSFSHA" ]; then echo "СТОП: $MSF не тот, что напечатал M3 (sha256 не $MSFSHA)"; return 1; fi
    echo "отпечатки M3: $MSF, sha256 = MSF_SHA256 из вывода M3"
    if [ "$EXE" != "$MW/install/mavros/lib/mavros/mavros_node" ]; then echo "СТОП: mavros_node не из $MW"; return 1; fi
    if [ "$NBW" != 2 ] || [ "$NOPT" != 6 ]; then echo 'СТОП: ждали из bench_ws ровно 2 (libmavros, libmavros_plugins) и из /opt ровно 6 (libmavconn, libmavros_extras_plugins, 4 библиотеки mavros_msgs)'; return 1; fi
    for n in libmavros.so libmavros_plugins.so; do
      if ! grep -q "  $MW/install/mavros/lib/$n\$" "$F"; then echo "СТОП: $n не из $MW"; return 1; fi
      if grep -q "  /opt/ros/jazzy/lib/$n\$" "$F"; then echo "СТОП: загружена и старая $n из /opt"; return 1; fi
    done
    for n in libmavconn.so libmavros_extras_plugins.so; do
      if ! grep -q "  /opt/ros/jazzy/lib/$n\$" "$F"; then echo "СТОП: не загружена $n из /opt"; return 1; fi
    done
    if ! grep -q "^$EXESUM  ./mavros/lib/mavros/mavros_node\$" "$MSF"; then echo "СТОП: сумма mavros_node не та, что в $MSF (M3)"; return 1; fi
    while read -r s f; do
      case "$f" in
        "$MW/install/"*)
          if ! grep -q "^$s  ./${f#"$MW/install/"}\$" "$MSF"; then echo "СТОП: сумма $f не та, что в $MSF (M3)"; return 1; fi ;;
        *)
          if ! grep -q "^$s " "$BEF"; then echo "СТОП: сумма $f не та, что в 7.1 этой сессии ($BEF)"; return 1; fi ;;
      esac
    done < "$F"
    for p in libmavconn.so:9107f99e66b88ed84bf9cddaed0a24fc54ee32997c24f6a229a608a2033dacb4 \
             libmavros_extras_plugins.so:b0f5b5862f62a4ebfe24bef8fddca45123f20772ae50796ec8b837a751f6d3a7; do   # часть 0а, 28.10: MAVROS apt 2.14.0
      if ! grep -q "^${p#*:}  /opt/ros/jazzy/lib/${p%%:*}\$" "$F"; then echo "СТОП: ${p%%:*} не та, что в части 0а (MAVROS apt 2.14.0)"; return 1; fi
    done
    MLAB="оверлей $MW (mavros_node, libmavros, libmavros_plugins) + apt 2.14 из /opt (libmavconn, extras, msgs)"
  else
    # ниже — проверки MAVROS из плана 7.4 без изменений; строже плана только проверка выше (NOPT + NBW = NALL)
    if [ "$EXE" != /opt/ros/jazzy/lib/mavros/mavros_node ]; then echo 'СТОП: mavros_node не из /opt/ros/jazzy'; return 1; fi
    if [ "$NBW" != 0 ] || [ "$NOPT" = 0 ]; then echo 'СТОП: библиотеки MAVROS не только из /opt/ros/jazzy'; return 1; fi
    for n in libmavconn libmavros.so libmavros_plugins libmavros_extras_plugins; do
      if ! grep -q "/$n" "$F"; then echo "СТОП: не загружена $n"; return 1; fi
    done
    while read -r s f; do
      if ! grep -q "^$s " "$BEF"; then echo "СТОП: сумма $f не та, что в 7.1 этой сессии ($BEF)"; return 1; fi
    done < "$F"
    for p in libmavconn.so:9107f99e66b88ed84bf9cddaed0a24fc54ee32997c24f6a229a608a2033dacb4 \
             libmavros.so:6a58ea97c0f21b4fbb76aeaab3232cdcaacd934adcedbd1d9695137c074b5c25 \
             libmavros_plugins.so:59aab8626f0b55aaa46394f92bcf6fec9ce83e2d1f40f58af0d933713c5728d2 \
             libmavros_extras_plugins.so:b0f5b5862f62a4ebfe24bef8fddca45123f20772ae50796ec8b837a751f6d3a7; do   # часть 0а, 28.10: MAVROS apt 2.14.0
      if ! grep -q "^${p#*:}  /opt/ros/jazzy/lib/${p%%:*}\$" "$F"; then echo "СТОП: ${p%%:*} не та, что в части 0а (MAVROS apt 2.14.0)"; return 1; fi
    done
    MLAB="apt 2.14 из /opt"
  fi
  echo "ros-jazzy-mavros: $MV"
  if [ "$MV" != 2.14.0-1noble.20260125.001824 ]; then echo "СТОП: ros-jazzy-mavros $MV, а в части 0а 2.14.0-1noble.20260125.001824"; return 1; fi
  echo "${V:-vpe_fix.py: нет}"
  if [ "$NV" != 1 ]; then echo "СТОП: vpe_fix.py не ровно один ($NV)"; return 1; fi
  echo "setpoint_freshness: $NSF"
  if [ "$B" = port ]; then
    case "$V" in *' /home/lb/bench_ws/port/install/bumblebee/lib/bumblebee/vpe_fix.py'*) ;; *) echo 'СТОП: vpe_fix.py не из bench_ws/port'; return 1 ;; esac
    if [ "$NSF" != 1 ]; then echo 'СТОП: setpoint_freshness не ровно один'; return 1; fi
  else
    case "$V" in *' /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/vpe_fix.py'*) ;; *) echo 'СТОП: vpe_fix.py не из ros2_ws'; return 1 ;; esac
    if [ "$NSF" != 0 ]; then echo 'СТОП: setpoint_freshness работает, а пакет должен быть релизный'; return 1; fi
  fi
  echo "проверки 7.4 сошлись: STEP=$STEP, MAVROS=$MLAB, пакет=$B"
}

rc3m_cpu_eval() {  # STEP CX10 (CPU now, 0.1 % of one core) APTF (m6 file with CPU_APT_X10)
  local STEP="$1" CX10="$2" APTF="$3" AX10
  case "$STEP" in
    UM|UM_*) ;;
    *) echo "ЦП: только запись (порог bp02 — только при STEP=UM, как У1 редакции 9)"; return 0 ;;
  esac
  if [ ! -f "$APTF" ]; then echo "СТОП: нет $APTF (замер ЦП apt в 7.1, m6_cpu_apt.sh): порог bp02 не проверить"; return 1; fi
  AX10=$(sed -n 's/^CPU_APT_X10=\([0-9][0-9]*\)$/\1/p' "$APTF")
  if [ -z "$AX10" ]; then echo "СТОП: в $APTF нет строки CPU_APT_X10"; return 1; fi
  echo "ЦП: сейчас $((CX10 / 10)).$((CX10 % 10))%, apt в 7.1 $((AX10 / 10)).$((AX10 % 10))%; порог: не больше 50% и не больше 2 × apt"
  if [ "$CX10" -gt 500 ]; then echo "СТОП: ЦП mavros_node больше 50% одного ядра (порог bp02, редакция 9 У1)"; return 1; fi
  if [ "$CX10" -gt $((2 * AX10)) ]; then echo "СТОП: ЦП mavros_node больше чем в 2 раза выше apt (порог bp02, редакция 9 У1)"; return 1; fi
  echo "ЦП ГОТОВО"
}

if [ -n "$RC3M_SOURCE_ONLY" ]; then return 0 2>/dev/null || exit 0; fi

echo "=== $(date '+%F %T') 7.4 (rc3): STEP=$STEP"
( set -eo pipefail
  [ -n "$BD" ]
  [ -d "$BD" ]
  [ "$(hostname)" = "bumblebee-20ec" ]
  [ -n "$STEP" ]
  [ -f "$BD/00_before.txt" ]                                            # 7.1 этой сессии: суммы библиотек MAVROS apt
  case "$STEP" in
    rollback|rollback_*) ;;
    *) if ! printf '%s' "${RC3M_MSF_SHA256:-}" | grep -qxE '[0-9a-f]{64}'; then echo "СТОП: нет RC3M_MSF_SHA256 (строка MSF_SHA256= из вывода M3 этой сессии); файл $BD/mavros_libs_$STEP.txt не создан, повтор с тем же STEP"; exit 1; fi ;;
  esac
  F="$BD/mavros_libs_$STEP.txt"
  [ ! -e "$F" ]                                                         # имя уже занято — суффикс _2, _3
  P=$(pgrep -x mavros_node || true)
  if [ -z "$P" ]; then
    case "$STEP" in
      kill[0-9]*) echo "СТОП: mavros_node нет. Повтор с тем же STEP=$STEP через 10 с (не больше 3 раз) — только если дрон разоружён и в окне 1 после новой CON: Got HEARTBEAT нет нового process has died; иначе стоп по п. 4.3 и 9.2" ;;
      *)          echo 'СТОП: mavros_node нет' ;;
    esac
    exit 1
  fi
  echo "PID=$P"
  [ "$(echo $P | wc -w)" = 1 ]                                          # ровно один номер
  EXE=$(readlink -f "/proc/$P/exe")
  echo "readlink: $EXE"
  T=$(mktemp)
  grep -oE '/[^ ]*(mavros|mavconn)[^ ]*\.so[^ ]*' "/proc/$P/maps" | sort -u > "$T"
  xargs sha256sum < "$T" | tee "$F"
  EXESUM=$(sha256sum "$EXE" | cut -d' ' -f1)
  echo "sha256 mavros_node: $EXESUM"
  MV=$(dpkg-query -W -f='${Version}' ros-jazzy-mavros)
  ros2 pkg prefix mavros
  ros2 pkg prefix bumblebee
  pgrep -af '/lib/bumblebee/simple_offboard( |$)' || echo 'simple_offboard: нет'
  V=$(pgrep -af '/lib/bumblebee/vpe_fix\.py' || true)                   # только по пути исполняемого файла
  NV=$(pgrep -fc '/lib/bumblebee/vpe_fix\.py' || true)
  NSF=$(pgrep -fc '/lib/bumblebee/setpoint_freshness\.py' || true)       # не просто «setpoint_freshness»: это слово есть и в строке simple_offboard
  # ЦП mavros_node, в десятых долях % одного ядра. STEP=UM*: критерий bp02 из редакции 9 (У1), 30 с, как замер apt (m6);
  # остальные шаги: только запись, 10 с (как 30.10)
  case "$STEP" in UM|UM_*) CS=30 ;; *) CS=10 ;; esac
  HZ=$(getconf CLK_TCK)
  a=$(awk '{print $14+$15}' "/proc/$P/stat"); sleep "$CS"; b=$(awk '{print $14+$15}' "/proc/$P/stat" 2>/dev/null || echo "$a")
  if [ "$(readlink -f "/proc/$P/exe" 2>/dev/null)" != "$EXE" ]; then
    echo "mavros_node (PID $P) пропал во время замера ЦП"
    case "$STEP" in UM|UM_*) echo 'СТОП: порог ЦП bp02 не проверить'; exit 1 ;; esac
  fi
  CX10=$(( (b - a) * 1000 / (HZ * CS) ))
  echo "ЦП mavros_node за $CS с: $((CX10 / 10)).$((CX10 % 10))% одного ядра"
  rc3m_eval "$STEP" "$EXE" "$F" "$BD/00_before.txt" "$MSF_DEFAULT" "$MV" "$V" "$NV" "$NSF" "$EXESUM" "${RC3M_MSF_SHA256:-}"
  rc3m_cpu_eval "$STEP" "$CX10" "$BD/mavros_cpu_apt.txt"
  echo "7.4 ГОТОВО: STEP=$STEP, MAVROS=$MLAB, пакет=$B" )
RC=$?
if [ "$RC" != 0 ]; then echo "=== СТОП: 7.4 (rc3) не сошлась: по п. 4.3 и 9.2 (исключение — 'mavros_node нет' при STEP=kill…, см. план 7.4)"; exit 1; fi
echo RC3M_M5_OK
