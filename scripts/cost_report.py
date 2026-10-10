#!/usr/bin/env python3
"""成本看板：解析 /tmp/llm_usage.log，按天/模型汇总 token 和估算费用。"""
import sys
from collections import defaultdict
from datetime import datetime

# 模型价格 ($/1M tokens)，按 opencode-go 2026-10 水平估算
PRICES = {
    "longcat-2.5-preview-free": (0, 0),
    "step-5-preview-free": (0, 0),
    "deepseek-v4-flash": (0.15, 0.60),
    "deepseek-v4-pro": (0.66, 2.64),
    "deepseek-v4.1-flash": (0.15, 0.60),
}

def main():
    log = "/tmp/llm_usage.log"
    try:
        lines = open(log).read().strip().split("\n")
    except FileNotFoundError:
        print("暂无用量记录")
        return
    by_day_model = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # day -> model -> [prompt, completion]
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        ts, model = int(parts[0]), parts[1]
        pt = int(parts[2].split("=")[1])
        ct = int(parts[3].split("=")[1])
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        by_day_model[day][model][0] += pt
        by_day_model[day][model][1] += ct

    total_cost = 0
    for day in sorted(by_day_model):
        print(f"\n=== {day} ===")
        day_cost = 0
        for model in sorted(by_day_model[day]):
            pt, ct = by_day_model[day][model]
            pi, po = PRICES.get(model, (0, 0))
            cost = (pt * pi + ct * po) / 1_000_000
            day_cost += cost
            print(f"  {model}: prompt={pt:,} completion={ct:,} 费用=${cost:.4f}")
        print(f"  当日合计: ${day_cost:.4f}")
        total_cost += day_cost
    print(f"\n总费用: ${total_cost:.4f}")

if __name__ == "__main__":
    main()
