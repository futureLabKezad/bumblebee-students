#!/bin/bash
# mutation_check_r6.sh (Claude, 12.11.2026, набор r6) - «у тестов есть зубы»: портит по одному месту в копиях pi/r6_*.sh и проверяет,
# что tests/run_tests_r6_pi.sh это ловит (FAIL > 0). Набор не трогает: работает на копии в папке-аргументе. К дрону не обращается.
# Запуск (WSL): nice -n 19 ionice -c3 bash proverka_r6/mutation_check_r6.sh <папка для копий>
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:?нужна папка для копий}"
W=$(mktemp -d "$BASE/r6mut_XXXXXX")
ok=0; bad=0
mut() { # mut <имя> <файл в pi/> <sed-выражение> <что должно поймать>
  local n="$1" f="$2" ex="$3" what="$4" d="$W/$1"
  mkdir -p "$d/tests" && cp -r "$KIT/pi" "$KIT/camera_fullrow" "$d/" && cp "$KIT/tests/run_tests_r6_pi.sh" "$d/tests/"
  sed -i -e "$ex" "$d/pi/$f"
  if cmp -s "$KIT/pi/$f" "$d/pi/$f"; then echo "MUT $n: правка не применилась (sed ничего не изменил) - НЕ ПРОВЕРЕНО"; bad=$((bad+1)); return; fi
  bash "$d/tests/run_tests_r6_pi.sh" "$d" > "$d/out.txt" 2>&1
  nf=$(grep -c '^FAIL ' "$d/out.txt")
  if [ "$nf" -gt 0 ]; then ok=$((ok+1)); echo "MUT $n ($what): поймано, FAIL $nf: $(grep '^FAIL ' "$d/out.txt" | head -2 | cut -c1-140 | tr '\n' ' ')"
  else bad=$((bad+1)); echo "MUT $n ($what): НЕ ПОЙМАНО"; fi
}
mut M1 r6_pi_load.sh '/^\[ "\$(hostname)" = "bumblebee-20ec" \]/d' 'нет проверки имени хоста'
mut M2 r6_cam_verify.sh '/case "\$a" in \*BB_R6\*) path=""; node=""; break;; esac/d' 'свой процесс считается camera_fix'
mut M3 r6_sys_change.sh 's/systemctl mask --now \$UNITS/systemctl mask $UNITS/' 'mask без --now'
mut M4 r6_cost_phase.sh 's/ -r \/tf:=\/bench\/tf//' 'TF стендового детектора не уведён в /bench'
mut M5 r6_sys_check.sh 's/ros2 node list --no-daemon/ros2 node list/' 'ros2 без --no-daemon'
mut M6 r6_k1.sh '/\[ ! -e "\$K" \] || stop/d' 'нет отказа перезаписи папки K1'
mut M7 r6_cam_precheck.sh 's/|| why="\$why исполняется_не_оверлей_r2j(prefix=\${PFX:-none})"/|| true/' 'нет проверки исполняемого префикса'
mut M8 r6_sys_change.sh 's/\[ "\$e" = enabled \] || why="\$why \$u:is-enabled=\$e(ждали_enabled)"/true/' 'нет условия «до правки таймер enabled»'
echo "ИТОГ мутаций: поймано $ok, не поймано или не проверено $bad (копии: $W)"
[ "$bad" = 0 ]
