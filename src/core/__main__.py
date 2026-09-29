"""`python -m core` 入口：等价于 `core-agent`（console_scripts）。"""

from core.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
