#!/bin/bash
cd /work/t45_descent_20261111 || exit 1; bash -n run_t45.sh || exit 1
sha256sum make_descent.py descent_after_floor.py DIFF_r6_descent.txt run_t45.sh > SHA256SUMS.txt && cut -c1-16,65- SHA256SUMS.txt
