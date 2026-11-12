#!/bin/bash
H=/work/t49_sensor_pos_probe_20261111; mkdir -p $H/_aside_build1/af
for f in run_scenario7j.sh.new t49_phases.py DIFF_7h_7j.txt DIFF_t45_t49_phases.txt; do [ -e $H/$f ] && mv -n $H/$f $H/_aside_build1/; done
for f in $H/af/*; do mv -n $f $H/_aside_build1/af/; done; ls -R $H/_aside_build1
bash $H/build.sh
