#!/bin/bash
BASE=/home/hatch/workspace/daedalus-runner
pkill -f "proxy/proxy.py" 2>/dev/null
pkill -x daedalusd 2>/dev/null
sleep 1
nohup python3 $BASE/proxy/proxy.py > /tmp/proxy.log 2>&1 &
sleep 2
export OPENCODE_GO_DUMMY=dummy
export PATH="$HOME/.cargo/bin:$PATH"
# daemon 直连 127.0.0.1:8899，不走 egress 代理（reqwest 会被 https_proxy 干扰）
unset https_proxy http_proxy HTTPS_PROXY HTTP_PROXY
nohup $BASE/daemon/target/debug/daedalusd > /tmp/daedalusd.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:9800/api/health | head -c 120; echo
