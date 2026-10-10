from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
# 测试时跳过自动自愈（避免真实网络检查）
os.environ["DAEDALUS_NO_AUTOHEAL"] = "1"
