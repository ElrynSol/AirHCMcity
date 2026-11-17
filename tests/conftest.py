"""Thêm các thư mục mã nguồn vào sys.path để pytest import được train_model, predict, tinh_aqi..."""
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
for p in (GOC, GOC / 'backend', GOC / 'ml', GOC / 'data_pipeline'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
