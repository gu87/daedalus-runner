#!/bin/bash
# 自愈看门狗：每 60 秒检查 daemon 和代理，挂了就拉起来
BASE=/home/hatch/workspace/daedalus-runner
while true; do
  # 检查 daemon
  if ! curl -s -m 5 http://127.0.0.1:9800/api/health > /dev/null 2>&1; then
    echo "[$(date)] daemon 挂了，重启..." >> /tmp/watchdog.log
    bash $BASE/scripts/start-all.sh > /dev/null 2>&1
  fi
  # 检查代理
  if ! curl -s -m 5 http://127.0.0.1:8899/v1/models > /dev/null 2>&1; then
    echo "[$(date)] proxy 挂了，重启..." >> /tmp/watchdog.log
    bash $BASE/scripts/start-all.sh > /dev/null 2>&1
  fi
  sleep 60
done
