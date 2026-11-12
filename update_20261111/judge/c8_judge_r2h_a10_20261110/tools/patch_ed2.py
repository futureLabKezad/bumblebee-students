#!/usr/bin/env python3
"""patch_ed2.py - A10 edition 2 (T44, chat 1 18:52: S5 ProfileVpe, S4 test_entry_order). Texts and tests only.
The new executor/tests/test_entry_order.py is copied before this script runs. Each anchor must match once."""
from pathlib import Path

D = Path('/work/c8_judge_r2h_a10_20261110')


def rep(path, a, b):
    p = D / path
    t = p.read_text(encoding='utf-8')
    assert t.count(a) == 1, (path, a[:60], t.count(a))
    p.write_text(t.replace(a, b), encoding='utf-8')
    print('edited', path)


rep('tests/a10_checks.py',
    """assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/sitl_setup.py', 'executor/vision_c8.launch.py',
                 'executor/vpe_diagnostic_entry.py', 'executor/vpe_gate_diagnostic_p1.py'], diffs""",
    """assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/sitl_setup.py',
                 'executor/tests/test_entry_order.log', 'executor/tests/test_entry_order.py',   # ed.2 (review A10 S4): A10 composition
                 'executor/vision_c8.launch.py', 'executor/vpe_diagnostic_entry.py', 'executor/vpe_gate_diagnostic_p1.py'], diffs
_log = (D / 'executor/tests/test_entry_order.log').read_text()
assert 'ALL OK' in _log and 'PASS a10_order' in _log and 'PASS freshness_refuses_r2h_control' in _log, _log""")

rep('README.md',
    "- `executor/tests/test_entry_order.py` (не изменён против A9, в `test_c8_b2.sh` не запускается) собирает старый состав A9 с freshness. Для A10 он **устарел**; не правил, чтобы не трогать файлы исполнителя.",
    "- `executor/tests/test_entry_order.py` (в `test_c8_b2.sh` не запускается, пины его не закрепляют) в ред. 2 переписан под состав A10 (см. «Редакция 2»).")
rep('README.md',
    "- Класс профиля `ProfileVpe` на стенде проверен только статически",
    "- **ProfileVpe на дроне нет, публикацию и время позы он не меняет (доказано по коду).**\n"
    "  - На дроне `aruco.launch.py` r2h запускает `vpe_fix.py`, а его `main()` создаёт обычный `VpeFix` (8 потоков). В С8 узел — `ProfileVpe(VpeFix)` из `vpe_profile_optin.make_node_class`.\n"
    "  - ProfileVpe переопределяет только сервис параметров: `_handle_set_param`, `_handle_revert_all`, `_restore_one`, `_param_set_once`, `_arm_ttl`, `_initial_pull_tick`, restore. Записи параметров в С8 идут через профиль и сырой мост — это и есть то, что проверяет судья (журнал профиля `profile19`).\n"
    "  - Ни один метод пути позы не переопределён: `aruco_map_callback`, `publish_timer`, ворота, `_reentry_pose`, `get_clock`.\n"
    "  - Отличия от дрона вне позы: 4 потока исполнителя вместо 8, таймер 0,05 с restore и колбэки сырого MAVLink. Это может влиять только на расписание потоков (возможно).\n"
    "  - Судья читает журнал профиля, поэтому ProfileVpe остаётся.\n"
    "- Класс профиля `ProfileVpe` на стенде проверен только статически")
rep('README.md', "## Как запускать",
    "## Редакция 2 (10.11, ~19:00; T44, вопрос чата 1 про S5/S4)\n"
    "- Что изменено:\n"
    "  - README — строки о ProfileVpe (выше);\n"
    "  - `executor/tests/test_entry_order.py` переписан под состав A10: MRO = ProfileVpe → VpeFix, `_evaluate_gate` = обёртка диагностики, нет FreshnessMixin, ProfileVpe не переопределяет путь позы, sha vpe_fix = TARGET_SHA256. Контроль: оставленный в кандидате freshness отвергает vpe_fix r2h. Журнал `test_entry_order.log`: ALL OK;\n"
    "  - `tests/a10_checks.py` учитывает эти два файла.\n"
    "- Код прогона, пины (9ec805e7), манифест кандидата, пускач и судья **не изменились**: пины этот тест не закрепляют.\n"
    "- Ред. 1 (README, PROGRESS, SHA256SUMS.txt ef28f2ee, test_entry_order.*, a10_checks.py) — в `notes/_ed1/`.\n\n"
    "## Как запускать")
