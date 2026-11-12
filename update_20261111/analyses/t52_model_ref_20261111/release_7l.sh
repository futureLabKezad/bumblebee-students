#!/bin/bash
cd /work/t52_model_ref_20261111 || exit 1
sha256sum REVIEW_7l.md >> REVIEW_SHA256.txt
grep -q "пускач 7l" /work/REVIEW_LOCK.txt && mv -n /work/REVIEW_LOCK.txt /work/_aside_locks_20261110/REVIEW_LOCK_released_$(date +%H%M%S)_7l.txt && echo LOCK_RELEASED
sed -i "s|^task: .*|task: НЕ ЗАЧЁТ: T52 поворот на r2j (4074+v2) и база (4070+v1, r2hf), run_t52b.sh, 11.11 14:0x|" /work/SIM_LOCK.txt
echo "- 14:0x REVIEW_7l.md: GO (7l ac7b97bd). Замок освобождён. run_t52b.sh запущен." >> /work/goal_series_20261109/PROGRESS.md
