#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
免费模式：取消会员/点数/额度检查。
"""

import json


def main():
    print(json.dumps({
        "free_mode": True,
        "membership": "free",
        "quota": "unlimited",
        "message": "当前为免费模式，所有功能开放。"
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()