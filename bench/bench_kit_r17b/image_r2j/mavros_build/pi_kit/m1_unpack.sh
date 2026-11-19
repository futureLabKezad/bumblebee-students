#!/bin/bash
# rc3 MAVROS overlay, step M1 (Pi): unpack the git bundle of the chosen backport into ~/bench_ws/mavros/src and check it.
# Claude, 30.10.2026; v2 02.11.2026: if the Pi has no git (not proven by the inventory of parts 0а/0б/1), the same tag is
# taken from the git archive mavros_bp02_src_d63a236.tar.gz (copied byte for byte from bench_plan_v2/to_drone_rc2,
# PROVENANCE there): commit id from its pax header + sha256 of every file + exact file count. With git: as v1.
# r2 02.11.2026 (review of 02.11; old text: m1_unpack.sh.r1): the incoming folder must hold exactly the files listed in
# TRANSFER_SHA256SUMS.txt plus that file (old *.r1 copies or any other file there -> stop).
# Folder on the PC: /work/pc_inventory_20261019/rc3_mavros_pi_20261030 (README_RU.md).
# Reads only ~/bench_ws/incoming/rc3_mavros; creates only ~/bench_ws/mavros/src, ~/bench_ws/mavros_deps (both must not
# exist) and ~/bench_ws/mavros_src_mode.txt. Never overwrites, never deletes, no sudo, no network. Last line: RC3M_M1_OK.
# Env (dry run on the PC only): RC3M_HOST (expected hostname, default bumblebee-20ec), RC3M_INC (incoming folder),
# RC3M_NOGIT=1 (test of the no-git path on the PC).
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
INC="${RC3M_INC:-$HOME/bench_ws/incoming/rc3_mavros}"
export INC HOST_EXPECTED RC3M_NOGIT
echo "=== $(date '+%F %T') M1: исходники MAVROS из git bundle"
( set -eo pipefail
  [ "$(hostname)" = "$HOST_EXPECTED" ]
  [ -d "$INC" ]
  cd "$INC"
  sha256sum -c --quiet TRANSFER_SHA256SUMS.txt                        # все файлы переноса целы
  EXTRA=$(LC_ALL=C comm -23 <(ls -A | LC_ALL=C sort) <({ awk '{print $2}' TRANSFER_SHA256SUMS.txt; echo TRANSFER_SHA256SUMS.txt; } | LC_ALL=C sort))
  if [ -n "$EXTRA" ]; then echo "СТОП: в $INC лишние файлы (переносятся только файлы из TRANSFER_SHA256SUMS.txt): $(echo $EXTRA)"; exit 1; fi
  echo "в папке переноса ровно $(wc -l < TRANSFER_SHA256SUMS.txt) файлов из списка + сам список; sha256 списка: $(sha256sum < TRANSFER_SHA256SUMS.txt | cut -d' ' -f1)"
  tag=$(sed -n 's/^tag=//p' EXPECTED_SRC.txt)                         # метка, коммит, дерево, число файлов
  commit=$(sed -n 's/^commit=//p' EXPECTED_SRC.txt)
  tree=$(sed -n 's/^tree=//p' EXPECTED_SRC.txt)
  files=$(sed -n 's/^files=//p' EXPECTED_SRC.txt)
  [ -n "$tag" ]
  [ "${#commit}" = 40 ]
  [ "${#tree}" = 40 ]
  [ -n "$files" ]
  case "$tag" in backport-02) BN=mavros_bp02_d63a236; TB=mavros_bp02_src_d63a236.tar.gz ;; *) echo "СТОП: неизвестная метка $tag"; exit 1 ;; esac
  [ -f "$BN.bundle" ]
  [ -f "${BN}_files.sha256" ]
  [ -f "$TB" ]
  W="$HOME/bench_ws/mavros"
  DEPS="$HOME/bench_ws/mavros_deps"
  MODEF="$HOME/bench_ws/mavros_src_mode.txt"
  if [ -e "$W" ]; then echo "СТОП: $W уже есть (M1 не повторяется; прислать Claude ls -la $W)"; exit 1; fi
  if [ -e "$DEPS" ]; then echo "СТОП: $DEPS уже есть (прислать Claude)"; exit 1; fi
  if [ -e "$MODEF" ]; then echo "СТОП: $MODEF уже есть (прислать Claude)"; exit 1; fi
  df -h "$HOME" | tail -1
  if command -v git >/dev/null 2>&1 && [ -z "$RC3M_NOGIT" ]; then
    command -v git
    git --version
    mkdir -p "$W/src/mavros-source"
    cd "$W/src/mavros-source"
    git init -q
    git bundle verify "$INC/$BN.bundle"                                  # нужен репозиторий: проверка после git init
    git fetch -q --no-tags "$INC/$BN.bundle" 'refs/tags/*:refs/tags/*'
    git -c advice.detachedHead=false checkout -q --detach "$commit"
    H=$(git rev-parse HEAD)
    echo "HEAD: $H"
    [ "$H" = "$commit" ]
    [ "$(git rev-parse "refs/tags/$tag^{commit}")" = "$commit" ]
    [ "$(git rev-parse 'HEAD^{tree}')" = "$tree" ]
    [ -z "$(git status --porcelain --untracked-files=all)" ]             # дерево = метка, лишних файлов нет
    [ "$(git ls-files | wc -l)" = "$files" ]
    git log --oneline -6
    MODE=git
  else
    echo "git на этом Pi нет: та же метка из git archive $TB (коммит из заголовка архива, sha256 каждого файла)"
    hc=$(gzip -dc "$INC/$TB" | head -c 4096 | grep -a -o 'comment=[0-9a-f]\{40\}' | head -1 | cut -d= -f2 || true)
    echo "коммит в заголовке архива: $hc"
    [ "$hc" = "$commit" ]
    mkdir -p "$W/src/mavros-source"
    cd "$W/src/mavros-source"
    tar -xzf "$INC/$TB"
    [ ! -e .git ]
    MODE=tar
  fi
  cd "$W/src/mavros-source"
  [ "$(find . -path ./.git -prune -o -type f -print | wc -l)" = "$files" ]  # ровно эти файлы, лишних нет
  [ "$(wc -l < "$INC/${BN}_files.sha256")" = "$files" ]
  sha256sum -c --quiet "$INC/${BN}_files.sha256"                      # каждый файл = список с ПК (sha256)
  for p in libmavconn mavros_msgs mavros mavros_extras; do [ -f "$p/package.xml" ]; done
  grep -q '<version>2.14.0</version>' mavros/package.xml
  { echo "MODE=$MODE"; echo "commit=$commit"; echo "files=$files"; } > "$MODEF"
  # angles: только заголовки для сборки (на дроне ros-jazzy-angles нет; apt не трогаем). Не ELF, не подключается при работе.
  mkdir -p "$DEPS"
  tar -xzf "$INC/angles_1.16.1_buildprefix.tar.gz" -C "$DEPS"
  ( cd "$DEPS" && sha256sum -c --quiet "$INC/angles_1.16.1_files.sha256" )
  [ "$(find "$DEPS" -type f | wc -l)" = "$(wc -l < "$INC/angles_1.16.1_files.sha256")" ]
  [ -f "$DEPS/opt/ros/jazzy/include/angles/angles/angles.h" ]
  echo "ИСХОДНИКИ MAVROS ГОТОВО ($MODE): $tag $commit (дерево $tree, файлов $files), angles в $DEPS" )
RC=$?
if [ "$RC" != 0 ]; then echo "=== СТОП: M1 не прошёл (код $RC). Ничего не повторять, прислать Claude этот вывод."; exit 1; fi
echo RC3M_M1_OK
