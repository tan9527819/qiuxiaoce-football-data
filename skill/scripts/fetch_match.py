#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询赛程或单场全景数据。

免费模式：
1. 优先读取本地缓存，不需要 API Key。
2. 本地没有数据时，只有配置了 API Key 才访问远程接口。
3. 没有 API Key 时不会调用第三方收费接口。
4. 保留原有输出结构和查询方式。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from local_store import LocalStore


BASE_URL = "https://www.qiuxiaoce.com/wp-json/abv2-creator/v1"
USER_AGENT = "QiuXiaoCe-Skill-Agent/2.5.0"


def get_api_key(cli_key=None):
    """读取 API Key；免费模式下允许为空。"""
    if cli_key:
        return cli_key.strip()

    return os.environ.get("QIUXIAOCE_API_KEY", "").strip() or None


def http_get(endpoint, key, params=None):
    """发送 GET 请求并返回 JSON。"""

    if not key:
        return {
            "error": True,
            "offline": True,
            "message": (
                "当前为免费本地模式，未配置 API Key。"
                "本地缓存没有该数据，因此暂时无法获取远程数据。"
            ),
        }

    url = BASE_URL + endpoint

    if params:
        url += "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "X-API-Key": key,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="ignore",
        )

        try:
            payload = json.loads(body)
            message = payload.get("message", body)
        except (ValueError, TypeError):
            message = body

        return {
            "error": True,
            "status": error.code,
            "message": message,
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
    ) as error:

        return {
            "error": True,
            "message": str(error),
        }


def compact_pack(response):
    """压缩 Match-Pack 响应，同时保留未知非空字段。"""

    pack = response.get("pack")

    if not isinstance(pack, dict):
        return {
            "error": True,
            "message": "接口响应缺少有效的 pack 对象。",
        }

    preferred_keys = [
        "fixture_id",
        "league_id",
        "league_name",
        "kickoff",
        "venue_name",
        "referee",
        "home_team_id",
        "away_team_id",
        "home_name",
        "away_name",
        "fixture",
        "match",
        "teams",
        "league",
        "standings",
        "form",
        "recent_form",
        "home_form",
        "away_form",
        "home_stats",
        "away_stats",
        "injuries",
        "home_injuries",
        "away_injuries",
        "predicted_lineups",
        "lineups",
        "home_coach",
        "away_coach",
        "advanced",
        "home_advanced",
        "away_advanced",
        "team_advanced_metrics",
        "player_advanced_metrics",
        "calculated_metrics",
        "h2h",
        "coaches",
        "tactical",
        "injury_impact",
        "market",
        "market_movements",
        "lottery_total_goals_odds",
        "_realtime_note",
    ]

    result = {
        "_summary": (
            "球小策单场全景紧凑包；"
            "预测字段与衍生评分需单独标注，"
            "缺失字段不得补造。"
        ),
        "fixture_id": response.get("fixture_id"),
        "meta": response.get("meta") or {},
    }

    consumed = set()

    for key in preferred_keys:
        value = pack.get(key)

        if value not in (
            None,
            "",
            [],
            {},
        ):
            result[key] = value
            consumed.add(key)

    other = {
        key: value
        for key, value in pack.items()
        if (
            key not in consumed
            and value not in (
                None,
                "",
                [],
                {},
            )
        )
    }

    if other:
        result["other_non_empty_fields"] = other

    return result


def fixture_team_name(fixture, side):
    """兼容不同赛程字段结构并提取球队名称。"""

    direct = (
        fixture.get(f"{side}_team_name")
        or fixture.get(f"{side}_team")
    )

    if isinstance(direct, str):
        return direct

    if isinstance(direct, dict):
        return str(
            direct.get("name") or ""
        )

    teams = fixture.get("teams")

    if (
        isinstance(teams, dict)
        and isinstance(teams.get(side), dict)
    ):
        return str(
            teams[side].get("name") or ""
        )

    return ""


def load_cached_data(store, endpoint, params=None):
    """优先读取本地缓存。"""

    try:
        return store.get(
            endpoint,
            params,
        )
    except Exception as error:
        return {
            "error": True,
            "message": f"读取本地缓存失败：{error}",
        }


def save_cached_data(store, endpoint, response, params=None):
    """安全保存数据到本地缓存。"""

    try:
        store.set(
            endpoint,
            response,
            params,
        )
    except Exception:
        pass


def main():
    """解析参数并执行赛程或 Match-Pack 查询。"""

    parser = argparse.ArgumentParser(
        description=(
            "球小策赛程定位与单场全景数据查询工具"
        )
    )

    parser.add_argument(
        "--key",
        help=(
            "可选 API Key。"
            "不填写时优先使用本地免费数据。"
        ),
    )

    parser.add_argument(
        "--date",
        help=(
            "比赛日期 YYYY-MM-DD，"
            "默认取本机当前日期"
        ),
    )

    parser.add_argument(
        "--team",
        help="用于筛选候选比赛的球队名称",
    )

    parser.add_argument(
        "--lottery-type",
        choices=[
            "all",
            "zucai",
            "beidan",
        ],
        default="all",
        help="赛程接口筛选参数",
    )

    parser.add_argument(
        "--pack",
        type=int,
        help=(
            "直接获取指定 fixture_id "
            "的 Match-Pack"
        ),
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="输出完整原始接口响应",
    )

    args = parser.parse_args()

    key = get_api_key(args.key)

    store = LocalStore()

    # =========================================================
    # 单场 Match-Pack
    # =========================================================

    if args.pack:

        endpoint = f"/match-pack/{args.pack}"

        # ① 免费模式优先读取本地
        response = load_cached_data(
            store,
            endpoint,
        )

        source = "local"

        # ② 本地没有，再判断是否允许访问远程
        if response is None:

            if not key:
                response = {
                    "error": True,
                    "offline": True,
                    "fixture_id": args.pack,
                    "message": (
                        "本地没有该场比赛数据。"
                        "当前没有配置 API Key，"
                        "因此不会调用第三方收费接口。"
                    ),
                }

            else:
                response = http_get(
                    endpoint,
                    key,
                )

                source = "api"

                if (
                    isinstance(response, dict)
                    and not response.get("error")
                ):
                    save_cached_data(
                        store,
                        endpoint,
                        response,
                    )

                    pack = (
                        response.get("pack")
                        if isinstance(
                            response.get("pack"),
                            dict,
                        )
                        else {}
                    )

                    try:
                        store.save_fixtures(
                            [pack],
                            endpoint,
                        )
                    except Exception:
                        pass

        if response.get("error"):

            print(
                json.dumps(
                    response,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            return 1

        output = (
            response
            if args.raw
            else compact_pack(response)
        )

        output["_source"] = source

        print(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2,
            )
        )

        return (
            1
            if output.get("error")
            else 0
        )

    # =========================================================
    # 赛程查询
    # =========================================================

    target_date = (
        args.date
        or datetime.now().strftime(
            "%Y-%m-%d"
        )
    )

    endpoint = "/fixtures"

    params = {
        "date": target_date,
        "lottery_type": args.lottery_type,
    }

    # ① 免费模式优先读取本地
    response = load_cached_data(
        store,
        endpoint,
        params,
    )

    source = "local"

    # ② 本地没有，再判断是否访问远程
    if response is None:

        if not key:

            response = {
                "error": True,
                "offline": True,
                "date": target_date,
                "message": (
                    "本地没有该日期的赛程数据。"
                    "当前没有配置 API Key，"
                    "因此不会调用第三方收费接口。"
                ),
            }

        else:

            response = http_get(
                endpoint,
                key,
                params,
            )

            source = "api"

            if (
                isinstance(response, dict)
                and not response.get("error")
            ):

                save_cached_data(
                    store,
                    endpoint,
                    response,
                    params,
                )

                try:
                    store.save_fixtures(
                        response.get("data") or [],
                        endpoint,
                    )
                except Exception:
                    pass

    if response.get("error"):

        print(
            json.dumps(
                response,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 1

    fixtures = (
        response.get("data", [])
        if isinstance(response, dict)
        else []
    )

    if not isinstance(fixtures, list):

        print(
            json.dumps(
                {
                    "error": True,
                    "message": (
                        "赛程接口返回的 "
                        "data 不是列表。"
                    ),
                },
                ensure_ascii=False,
            )
        )

        return 1

    # =========================================================
    # 球队筛选
    # =========================================================

    if args.team:

        term = args.team.casefold().strip()

        fixtures = [
            fixture
            for fixture in fixtures
            if (
                term
                in fixture_team_name(
                    fixture,
                    "home",
                ).casefold()
                or term
                in fixture_team_name(
                    fixture,
                    "away",
                ).casefold()
            )
        ]

    # =========================================================
    # 输出
    # =========================================================

    print(
        json.dumps(
            {
                "success": True,
                "date": response.get(
                    "date",
                    target_date,
                ),
                "count": len(fixtures),
                "fixtures": fixtures,
                "_source": source,
                "free_mode": True,
                "note": (
                    "当前采用免费优先模式："
                    "优先读取本地数据；"
                    "没有本地数据时，"
                    "未配置 API Key 不调用收费接口。"
                ),
                "filter_note": (
                    "球队名称仅用于筛选候选项，"
                    "后续查询必须使用 fixture_id。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())