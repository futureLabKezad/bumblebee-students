#!/bin/bash
# install_diff_check.sh - r2f -> r2g install binaries differ only by the build folder path and the GNU build-id (T39, chat 1).
# The two folder names have the same length: the r2f path is swapped for the r2g one byte-for-byte, then every remaining
# differing byte must lie inside the 20-byte .note.gnu.build-id (a hash of the build, paths included). Read-only.
F=/work/fixed_image_r2f_20261110/install/bumblebee/lib/bumblebee
G=/work/fixed_image_r2g_20261110/install/bumblebee/lib/bumblebee
T=$(mktemp -d); rc=0
for b in $(cd $G && ls); do
  if cmp -s $F/$b $G/$b; then echo "$b identical"; continue; fi
  LC_ALL=C sed "s/fixed_image_r2f_20261110/fixed_image_r2g_20261110/g" $F/$b > $T/$b
  off=$(readelf -SW $G/$b | awk "/\.note\.gnu\.build-id/{print \$5}")
  [ -n "$off" ] || { echo "$b: differs and has no build-id"; rc=1; continue; }
  s=$((16#$off + 16)); e=$((s + 19))
  n=$(cmp -l $T/$b $G/$b | wc -l)
  out=$(cmp -l $T/$b $G/$b | awk -v s=$s -v e=$e "{o=\$1-1; if (o<s || o>e) bad++} END {print bad+0}")
  echo "$b: path occurrences $(LC_ALL=C grep -c fixed_image_r2f_20261110 $F/$b), differing bytes after the path swap $n, outside build-id $out"
  [ "$out" = 0 ] || rc=1
done
rm -rf $T; [ $rc = 0 ] && echo "RESULT: only path + build-id" || echo "RESULT: OTHER DIFFERENCES"; exit $rc
