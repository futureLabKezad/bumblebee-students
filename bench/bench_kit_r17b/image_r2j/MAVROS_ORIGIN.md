# Происхождение MAVROS bp02 для дрона (Claude, 10.11.2026, по запросу чата 1, только по файлам в /work, без Pi)

Метки: **доказано** (проверено по файлу сейчас), **нет доказательства**.

## Исходники: доказано
- Тег `backport-02` = коммит `d63a23674dd80ff4525829ca4bd716bbcc773111` в `/work/ws_mavros214_bp02/src/mavros-source` (`git rev-parse HEAD`, `git describe --tags`).
- Пять файлов из `/work/goal_20261106/mavros_bp02_sources.tsv` (колонка sha256_bp02) сверены с этим деревом: все 5 совпали (сверка выполнена вечером 10.11, команда `sha256sum` по путям из таблицы).
- Для передачи на Pi подготовлены: `mavros_bp02_d63a236.bundle` (sha256 dd7825a2…), `mavros_bp02_src_d63a236.tar.gz` (eb3387d8…), список 374 файлов; `EXPECTED_SRC.txt`: tag=backport-02, commit=d63a236… (`/work/pc_inventory_20261019/rc3_mavros_pi_verify_r2_20261102/dry/home/bench_ws/incoming/rc3_mavros/`).

## Сборка для Pi: НЕТ доказательства
- Бинарников для Pi (arm64) в /work нет. Все собранные MAVROS на ПК — x86-64 (`ws_mavros214_bp02`, `ws_mavros214_bp02_rel`, сухой прогон `dry/home/bench_ws/mavros/install`; `file`: x86-64).
- Файл `MAVROS_ARM64_SHA256SUMS.txt` (3 суммы: c4864c5f…, deed2aed…, 51a9e325…), который я брал в набор из `/work/pc_inventory_20261019/rc3_mavros_pi_verify_r2_20261102/tests_m5/`, это ТЕСТОВЫЙ образец проверок m5: такие же файлы лежат в `tests_m5` (там же) рядом с `libs_badsum.txt`, `MAVROS_ARM64_SHA256SUMS_changed.txt`; суммы не совпадают ни с одной сборкой ПК. Как отпечатки настоящей сборки Pi они не годятся. **Поправка к моей прежней версии набора (r2 в первой выдаче): я принял этот файл за сборки для Pi; это было неверно.** Из check_gates он убран, копия отложена в сторону.
- Задуманный путь (README `rc3_mavros_pi_20261030`): MAVROS собирается на самом Pi из исходников (`m1_unpack.sh`, `m2_build.sh`, `m3_verify.sh` печатает отпечатки сборки, `m5_check74_rc3.sh`), подключается поверх apt-версии строкой в `start_bumblebee.sh`. Прогон 30.10 остановлен (`STOPPED_RUN_30_10.md`), результатов с настоящего Pi в /work я не нашёл.
- На дроне сейчас MAVROS 2.14 из apt без исправлений (ТАБЛО_ЦЕЛИ, п. 5).

## Что сделано в наборе r2
- `check_gates.ps1` требует в манифесте все 5 исходников bp02; «сборки для Pi» не принимаются.
- Шаг стенда `10_mavros_versiya.cmd` (ТОЛЬКО ЧТЕНИЕ): печатает версию MAVROS из apt, какой MAVROS реально активен (`ros2 pkg prefix mavros`), коммит из `~/bench_ws/mavros_src_mode.txt` и git, sha256 пяти исходных файлов на Pi и сверяет с mavros_bp02_sources.tsv; не d63a236 или не все 5 совпали, или активна apt-версия: СТОП (код 5). Непроверенные бинарники на дрон не идут.