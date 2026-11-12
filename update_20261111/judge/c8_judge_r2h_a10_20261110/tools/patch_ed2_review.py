#!/usr/bin/env python3
"""patch_ed2_review.py - A10 ed.2, notes of REVIEW_A10_ed2.md (S1, S2, S4: README text; S3 recorded, not done).
Also removes the stray last line "EOF'" the reviewer's shell left in reviews/REVIEW_A10_ed2.md (reported by the reviewer)."""
from pathlib import Path

D = Path('/work/c8_judge_r2h_a10_20261110')


def rep(path, a, b):
    p = D / path
    t = p.read_text(encoding='utf-8')
    assert t.count(a) == 1, (path, a[:60], t.count(a))
    p.write_text(t.replace(a, b), encoding='utf-8')
    print('edited', path)


rep('README.md',
    "- **ProfileVpe на дроне нет, публикацию и время позы он не меняет (доказано по коду).**\n",
    "- **ProfileVpe на дроне нет. Путь позы и формулу метки времени (`now()` в унаследованном `publish_timer`) он не меняет — доказано по коду. Моменты срабатывания таймера 30 Гц могут отличаться — возможно, не измерено.**\n")
rep('README.md',
    "  - Отличия от дрона вне позы: 4 потока исполнителя вместо 8, таймер 0,05 с restore и колбэки сырого MAVLink. Это может влиять только на расписание потоков (возможно).\n",
    "  - Отличия от дрона вне позы:\n"
    "    - 4 потока исполнителя вместо 8;\n"
    "    - таймер 0,05 с restore, два сервиса, колбэки сырого MAVLink;\n"
    "    - нет начального ParamPull;\n"
    "    - восстановление после снятия с охраны отложено и идёт в группе обработчиков, а не в группе по умолчанию.\n"
    "    Это может сдвигать моменты срабатывания таймера публикации (возможно, не измерено; на первом прогоне смотреть частоту публикации).\n")
rep('README.md',
    "  - `tests/a10_checks.py` учитывает эти два файла.\n",
    "  - `tests/a10_checks.py` учитывает эти два файла.\n"
    "  - Тест повторяет состав входа, а не читает `vpe_diagnostic_entry.py`; его проверка «нет FreshnessMixin» по построению всегда верна (проверка ред. 2, S2). Сам вход проверяют `a10_checks.py` (AST: A9 без трёх операторов freshness) и пункты 6–7 `test_c8_b2.sh` (d2_vpe_composition, d2_entry_pins). Отрицательный случай внутри самого теста (S3) не добавлял.\n"
    "  - Выход тестов ред. 2: `tests/out_185336` и `reviews/tests_out_185336/` (4 json, как `tests_out_184229` в ред. 1). Счёт 31/31 — из вывода `test_c8_b2.sh` в консоль, в out_185336 он не сохраняется (S4).\n"
    "- Проверка ред. 2 — `reviews/REVIEW_A10_ed2.md` (один агент, через замок): **принято с замечаниями**, обязательных правок нет. Разница с ред. 1 — ровно эти файлы. S1, S2, S4 внесены выше (текст). Последняя строка `EOF'` в файле проверки — след оболочки проверяющего, удалена по его сообщению.\n")

p = D / 'reviews/REVIEW_A10_ed2.md'
lines = p.read_text(encoding='utf-8').split('\n')
while lines and lines[-1].strip() == '':
    lines.pop()
assert lines[-1].strip() == "EOF'", lines[-1]
lines.pop()
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('removed stray EOF line from', p)
