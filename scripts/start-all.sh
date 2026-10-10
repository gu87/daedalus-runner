#!/bin/bash
# Daedalus 跑腿小弟启动脚本：先代理，后 daemon
pkill -f "daedalus-proxy/proxy.py" 2>/dev/null
pkill -f "target/debug/daedalusd" 2>/dev/null
sleep 1
nohup python3 /home/hatch/workspace/daedalus-proxy/proxy.py > /tmp/proxy.log 2>&1 &
sleep 2
export OPENCODE_GO_DUMMY=dummy
export PATH="$HOME/.cargo/bin:$PATH"
nohup /home/hatch/workspace/daedalus/target/debug/daedalusd > /tmp/daedalusd.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:9800/api/health | head -c 120; echo
