"""让 pytest 能从仓库根 import core / exporters / agents。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
