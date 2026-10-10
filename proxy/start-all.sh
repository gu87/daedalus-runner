#!/bin/bash
BASE=/home/hatch/workspace/daedalus-runner
pkill -f "daedalus-runner/proxy/proxy.py" 2>/dev/null
pkill -f "daedalus-runner/daemon/target/debug/daedalusd" 2>/dev/null
sleep 1
nohup python3 $BASE/proxy/proxy.py > /tmp/proxy.log 2>&1 &
sleep 2
export OPENCODE_GO_DUMMY=dummy
export PATH="$HOME/.cargo/bin:$PATH"
nohup $BASE/daemon/target/debug/daedalusd > /tmp/daedalusd.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:9800/api/health | head -c 120; echo
