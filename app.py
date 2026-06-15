from __future__ import annotations

import re
from typing import Any

from flask import Flask, render_template, request

from test import (
    URL,
    build_category_blocks,
    filter_items,
    filter_items_by_category_options,
    filter_items_by_group,
    filter_items_by_platform,
    filter_items_by_price,
    filter_items_by_promo,
    filter_groups_by_platform,
    get_category_filters,
    is_single_select_category_filter,
    get_category_brands,
    get_category_groups,
    get_platform_filter_mode,
    get_category_numeric_filters,
    parse_numeric_spec_inputs,
    filter_items_by_numeric_specs,
    filter_items_by_white,
    group_items_by_promo_deadline,
    ensure_promo_deadline,
    normalize_platform,
    normalize_category_key,
    extract_notebook_values,
    get_notebook_field_defs,
    COOLER_KEYWORD_SHORTCUTS,
    html_to_lines,
    infer_brands,
    parse_items_from_block,
    fetch_html,
)

app = Flask(__name__)

_SUFFIX_TRIM_PATTERNS = (
    re.compile(r"\s*【[^】]*】\s*$"),
    re.compile(r"\s*\([^)]*\)\s*$"),
    re.compile(r"\s*（[^）]*）\s*$"),
)


def shorten_filter_label(name: str) -> str:
    """縮短篩選標籤：去掉尾端【】、()、（）等後綴。"""
    if not name:
        return name
    s = name.strip()
    changed = True
    while changed:
        changed = False
        for pattern in _SUFFIX_TRIM_PATTERNS:
            new_s = pattern.sub("", s)
            if new_s != s:
                s = new_s.strip()
                changed = True
    return s or name


app.jinja_env.filters["shorten_label"] = shorten_filter_label


@app.template_filter("notebook_specs")
def notebook_specs_filter(item: dict[str, Any]) -> dict[str, str]:
    return extract_notebook_values(item.get("category", ""), item.get("name", ""))


def parse_price(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    value = raw.replace(",", "")
    if not value.isdigit():
        return None
    return int(value)


@app.route("/", methods=["GET"])
def index() -> str:
    error = ""
    items: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    categories: list[str] = []
    brands: list[str] = []
    category_display = "全部類別"
    show_category = True

    selected_category = request.args.get("category", "__ALL__")
    selected_brand = request.args.get("brand", "").strip()
    keyword = request.args.get("keyword", "").strip()
    want_white = request.args.get("want_white") == "1"
    bargain_mode = request.args.get("bargain") == "1"
    min_price_raw = request.args.get("min_price", "").strip()
    max_price_raw = request.args.get("max_price", "").strip()
    min_price = parse_price(min_price_raw)
    max_price = parse_price(max_price_raw)

    if (min_price_raw and min_price is None) or (max_price_raw and max_price is None):
        error = "價格格式錯誤，請輸入數字（可含逗號）。"
    elif min_price is not None and max_price is not None and min_price > max_price:
        error = "最低價不能大於最高價。"

    try:
        html = fetch_html(URL)
        lines = html_to_lines(html)
        category_blocks = build_category_blocks(lines)
    except Exception as e:
        return render_template(
            "index.html",
            error=f"抓取資料失敗：{e}",
            categories=[],
            category_platform_modes={},
            category_labels={"__ALL__": "全部類別"},
            brands=[],
            results=[],
            show_category=True,
            category_display="全部類別",
            selected_category=selected_category,
            selected_brand="",
            selected_category_filters={},
            category_filter_defs={},
            category_groups=[],
            selected_groups=[],
            platform_filter_mode=None,
            selected_platform="",
            numeric_filter_defs=[],
            selected_numeric_specs={},
            keyword=keyword,
            want_white=False,
            bargain_mode=False,
            result_groups=[],
            show_cooler_keyword_shortcuts=False,
            cooler_keyword_shortcuts=COOLER_KEYWORD_SHORTCUTS,
            notebook_fields=get_notebook_field_defs(),
            min_price_raw=min_price_raw,
            max_price_raw=max_price_raw,
        )

    categories = list(category_blocks.keys())

    selected_category_filters: dict[str, list[str]] = {}
    category_filter_defs: dict[str, list[str]] = {}
    category_groups: list[str] = []
    selected_groups: list[str] = []
    platform_filter_mode: str | None = None
    selected_platform = ""
    numeric_filter_defs: list[dict[str, Any]] = []
    selected_numeric_specs: dict[str, str] = {}
    result_groups: list[dict[str, Any]] = []

    if selected_category == "__ALL__":
        category_display = "全部類別"
        show_category = True
        seen = set()
        for cat_name, block_lines in category_blocks.items():
            for item in parse_items_from_block(block_lines, category_name=cat_name):
                key = (item["name"], item["price"])
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    elif selected_category in category_blocks:
        category_display = selected_category
        show_category = False
        items = parse_items_from_block(
            category_blocks[selected_category], category_name=selected_category
        )

        all_groups = get_category_groups(items)
        platform_filter_mode = get_platform_filter_mode(category_display)
        if platform_filter_mode:
            selected_platform = normalize_platform(
                request.args.get("platform", ""),
                platform_filter_mode,
            )
            items = filter_items_by_platform(items, selected_platform)
            category_groups = filter_groups_by_platform(all_groups, selected_platform)
        else:
            selected_platform = ""
            category_groups = all_groups

        selected_groups = request.args.getlist("group")
        selected_groups = [x for x in selected_groups if x in category_groups]
        items = filter_items_by_group(items, selected_groups)

        category_filter_defs = get_category_filters(category_display)
        for filter_title, filter_options in category_filter_defs.items():
            field_name = f"cf_{filter_title}"
            if is_single_select_category_filter(filter_title):
                raw = request.args.get(field_name, "").strip()
                selected = [raw] if raw in filter_options else []
            else:
                selected = request.args.getlist(field_name)
                selected = [x for x in selected if x in filter_options]
            if selected:
                selected_category_filters[filter_title] = selected

        items = filter_items_by_category_options(items, selected_category_filters)

        numeric_filter_defs = get_category_numeric_filters(category_display)
        if numeric_filter_defs and not error:
            raw_spec_values = {
                fdef["field"]: request.args.get(f"spec_{fdef['field']}", "").strip()
                for fdef in numeric_filter_defs
            }
            selected_numeric_specs, spec_error = parse_numeric_spec_inputs(
                category_display,
                raw_spec_values,
            )
            if spec_error:
                error = spec_error
            elif selected_numeric_specs:
                items = filter_items_by_numeric_specs(items, selected_numeric_specs)
    else:
        error = "選擇的分類不存在，請重新選擇。"

    if not show_category:
        brands = get_category_brands(category_display)
        if not brands:
            brands = infer_brands(items)[:20]
        if selected_brand and selected_brand not in brands:
            selected_brand = ""
    else:
        selected_brand = ""

    if not error:
        items = filter_items_by_price(items, min_price=min_price, max_price=max_price)

        results = filter_items(items, keyword=keyword, brand=selected_brand)

        if want_white and not show_category:
            results = filter_items_by_white(results)
        elif show_category:
            want_white = False

        for item in results:
            ensure_promo_deadline(item)

        promo_results = filter_items_by_promo(results, promo_only=True)
        result_groups = group_items_by_promo_deadline(promo_results)

    category_platform_modes = {
        c: get_platform_filter_mode(c) or ""
        for c in categories
    }
    category_labels = {"__ALL__": "全部類別", **{c: c for c in categories}}

    return render_template(
        "index.html",
        error=error,
        categories=categories,
        category_platform_modes=category_platform_modes,
        brands=brands,
        results=results,
        show_category=show_category,
        category_display=category_display,
        selected_category=selected_category,
        selected_brand=selected_brand,
        selected_category_filters=selected_category_filters,
        category_filter_defs=category_filter_defs,
        category_groups=category_groups,
        selected_groups=selected_groups,
        platform_filter_mode=platform_filter_mode,
        selected_platform=selected_platform,
        numeric_filter_defs=numeric_filter_defs,
        selected_numeric_specs=selected_numeric_specs,
        keyword=keyword,
        want_white=want_white,
        show_cooler_keyword_shortcuts=normalize_category_key(category_display) == "散熱器",
        cooler_keyword_shortcuts=COOLER_KEYWORD_SHORTCUTS,
        min_price_raw=min_price_raw,
        max_price_raw=max_price_raw,
        category_labels=category_labels,
        bargain_mode=bargain_mode,
        result_groups=result_groups,
        notebook_fields=get_notebook_field_defs(),
    )


if __name__ == "__main__":
    app.run(debug=True)
