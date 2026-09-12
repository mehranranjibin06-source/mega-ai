#!/usr/bin/env python3
"""
اجرای مستقل «مدل نمایشی داخلی» روی پورت 8123 — برای تست کل خط تولید بدون هزینه:

  python tests/mock_llm.py &
  export OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:8123/v1
  python cli.py "هر پرامپتی"
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mega.demo_model import DEMO_MODELS, app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MOCK_PORT", "8123"))
    print(f"مدل نمایشی: http://127.0.0.1:{port}/v1  ·  مدل‌ها: {', '.join(DEMO_MODELS)}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
