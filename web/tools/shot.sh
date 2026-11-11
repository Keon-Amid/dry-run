#!/bin/bash
# usage: tools/shot.sh "<query string>" <out.png> [width] [height]   (dev helper: headless Chrome screenshot of the page)
OUT="$2"; W="${3:-1440}"; HH="${4:-900}"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=$W,$HH --virtual-time-budget=7000 --screenshot="$OUT" "http://localhost:5173/$1" >/dev/null 2>&1
ls -la "$OUT" 2>&1 | awk '{print $5, $9}'
