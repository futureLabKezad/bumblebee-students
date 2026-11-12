#!/usr/bin/python3 -I
"""line_stamp.py - goal step 5b (Claude, 09.11.2026). Reads one file only (stand helper).
Follows SRC (the script's own output file, which the script writes directly as before) and writes each new line to
DST with the wall-clock time it was first seen (polled every 0.1 s, so +-0.1 s). The script is not touched.
Stops when STOP exists and SRC has no new data. Usage: python3 -I line_stamp.py SRC DST STOP
"""
import os
import sys
import time


def main():
    src, dst, stop = sys.argv[1:4]
    pos, buf = 0, b''
    with open(dst, 'x', encoding='utf-8') as out:
        while True:
            data = b''
            if os.path.exists(src):
                with open(src, 'rb') as f:
                    f.seek(pos)
                    data = f.read()
                pos += len(data)
            if data:
                buf += data
                now = time.time()
                stamp = time.strftime('%H:%M:%S', time.localtime(now)) + '.%03d' % int((now % 1) * 1000)
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    out.write('%.3f %s %s\n' % (now, stamp, line.decode('utf-8', 'replace')))
                out.flush()
            elif os.path.exists(stop):
                if buf:
                    out.write('%.3f - %s\n' % (time.time(), buf.decode('utf-8', 'replace')))
                break
            time.sleep(0.1)


if __name__ == '__main__':
    main()
