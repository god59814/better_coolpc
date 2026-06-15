from __future__ import annotations

import re
import sys
import time
from collections import Counter
import unicodedata
from typing import Any

import requests
from bs4 import BeautifulSoup

URL = "https://www.coolpc.com.tw/evaluate.php"


def decode_coolpc_html(raw: bytes) -> str:
    for encoding in ("cp950", "big5hkscs", "big5", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("cp950", errors="replace")


def fetch_html(url: str) -> str:
    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.coolpc.com.tw/",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    last_error = None

    for attempt in range(3):
        try:
            resp = session.get(url, headers=headers, timeout=20)

            if resp.status_code == 503:
                print(f"[WARN] 第 {attempt + 1} 次請求 503，稍後重試...")
                time.sleep(2 + attempt * 2)
                continue

            resp.raise_for_status()

            # 原價屋 evaluate.php 宣告 charset=big5，不要用 requests 自動猜編碼
            return decode_coolpc_html(resp.content)

        except requests.RequestException as e:
            last_error = e
            print(f"[WARN] 第 {attempt + 1} 次請求失敗：{e}")
            time.sleep(2 + attempt * 2)

    raise RuntimeError(f"無法取得頁面：{last_error}")


def html_to_lines(html: str) -> list[str]:
    """
    不再把 HTML 轉成純文字行。
    原價屋 evaluate.php 應該保留 HTML 結構來解析。
    為了不大改 app.py / main() 的呼叫流程，這裡仍回傳 list[str]。
    """
    return [html]


def save_debug_files(html: str, lines: list[str]) -> None:
    with open("coolpc_debug_raw.html", "w", encoding="utf-8") as f:
        f.write(html)

    with open("coolpc_debug_lines.txt", "w", encoding="utf-8") as f:
        for i, line in enumerate(lines, start=1):
            f.write(f"{i:04d}: {line}\n")


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def try_extract_category_name(line: str) -> str | None:
    """
    盡量從文字行中抓出分類名。
    支援：
    1. 12, 顯示卡VGA
    2. 顯示卡VGA
    3. 顯示卡VGA 共有商品 143 樣，熱賣...
    """

    line = normalize_spaces(line)

    if "$" in line:
        return None

    # case 1: 12, 類別名
    m = re.match(r"^\d+\s*,\s*([^\$]{1,40})$", line)
    if m:
        name = m.group(1).strip()
        if valid_category_name(name):
            return name

    # case 2/3: 類別名 + 共有商品
    m = re.match(r"^(.{1,40}?)\s*共有商品\s*\d+\s*樣", line)
    if m:
        name = m.group(1).strip()
        if valid_category_name(name):
            return name

    # case 4: 單獨一行像「記憶體 RAM」
    if valid_category_name(line):
        return line

    return None


def valid_category_name(name: str) -> bool:
    name = normalize_spaces(name)

    if not name:
        return False

    if len(name) > 30:
        return False

    bad_keywords = [
        "共有商品",
        "熱賣",
        "圖片",
        "討論",
        "價格異動",
        "請輸入",
        "略過",
        "華碩",
        "技嘉",
        "微星",
        "撼訊",
        "藍寶",
        "單條",
        "雙通道",
        "DDR",
        "RTX",
        "RX",
        "GTX",
        "$",
    ]
    if any(k in name for k in bad_keywords):
        return False

    # 純數字不是分類
    if re.fullmatch(r"\d+", name):
        return False

    # 太像一般商品
    if len(name) < 2:
        return False

    # 至少要含中文、英數混合類型的分類風格
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", name):
        return False

    return True


def parse_categories(lines: list[str]) -> list[tuple[str, int]]:
    categories: list[tuple[str, int]] = []
    seen = set()

    for idx, line in enumerate(lines):
        name = try_extract_category_name(line)
        if not name:
            continue

        # 如果後面 1~3 行內有「共有商品」，可信度更高
        nearby = " ".join(lines[idx : idx + 4])
        score = 0
        if "共有商品" in nearby:
            score += 2
        if re.match(r"^\d+\s*,", line):
            score += 1

        if score == 0:
            continue

        if name not in seen:
            seen.add(name)
            categories.append((name, idx))

    return categories


def build_category_blocks(lines: list[str]) -> dict[str, list[dict[str, str]]]:
    """
    直接解析 evaluate.php 的表格結構：

    tbody#tbdy
      tr
        td.w = 類別編號
        td.t = 類別名稱
        select name=n1/n2/n3... = 商品選單（含 optgroup 分組）
    """
    html = "\n".join(lines)

    # 原價屋 HTML 比較老，html.parser 容易把 select/option 解析壞。
    soup = BeautifulSoup(html, "lxml")

    tbody = soup.find("tbody", id="tbdy")
    if tbody is None:
        return {}

    result: dict[str, list[dict[str, str]]] = {}

    for tr in tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)

        if len(tds) < 3:
            continue

        category_name = normalize_spaces(tds[1].get_text(" ", strip=True))
        if not category_name:
            continue

        select = tr.find("select", attrs={"name": re.compile(r"^n\d+$")})
        if select is None:
            continue

        block_items: list[dict[str, str]] = []

        # 原價屋 HTML 的 optgroup 常未正確關閉，會被 lxml 巢狀進第一個 optgroup，
        # 不能用 select.children 逐層走。改為對每個 option 找最近的 optgroup 祖先。
        for option in select.find_all("option"):
            if option.has_attr("disabled"):
                continue

            text = normalize_spaces(option.get_text(" ", strip=True))
            if not text or "共有商品" in text:
                continue

            og = option.find_parent("optgroup")
            group = normalize_spaces(og.get("label", "")) if og else ""

            block_items.append(
                {
                    "text": text,
                    "group": group,
                }
            )

        if block_items:
            result[category_name] = block_items

    return result


def extract_price(text: str) -> int | None:
    matches = re.findall(r"\$([0-9,]+)", text)
    if not matches:
        return None

    # 例如 $27950↘$25200，要取最後的 25200
    return int(matches[-1].replace(",", ""))


def extract_promo_deadline(text: str) -> str:
    """
    從原價屋商品文字中抓限時特價期限。
    會抓類似：特價到6/30、下殺到 6/30 23:59、任搭優惠到6/30
    """
    if not text:
        return ""

    patterns = [
        r"(?:限時)?特價\s*(?:到|至)\s*(\d{1,2}/\d{1,2})",
        r"下殺\s*(?:到|至)\s*(\d{1,2}/\d{1,2})",
        r"(?:任搭)?優惠\s*(?:到|至)\s*(\d{1,2}/\d{1,2})",
        r"促銷\s*(?:到|至)\s*(\d{1,2}/\d{1,2})",
        r"(?:特價|優惠|促銷|下殺).{0,12}?(?:到|至)\s*(\d{1,2}/\d{1,2})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)

    return ""


def ensure_promo_deadline(item: dict[str, Any]) -> str:
    """確保 item 已解析特價期限（含下殺到、優惠到等）。"""
    deadline = item.get("promo_deadline", "")
    if deadline:
        return deadline

    raw = item.get("raw", "") or item.get("name", "")
    deadline = extract_promo_deadline(raw)
    if deadline:
        item["promo_deadline"] = deadline
    return deadline


def is_promo_item(item: dict[str, Any]) -> bool:
    raw = item.get("raw", "") or item.get("name", "")
    return bool(ensure_promo_deadline(item)) or any(
        key in raw for key in ["特價", "限時", "促銷", "優惠", "下殺", "↘"]
    )


def filter_items_by_promo(
    items: list[dict[str, Any]],
    promo_only: bool = False,
    selected_deadlines: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected_deadlines = selected_deadlines or []

    results = []
    for item in items:
        if promo_only and not is_promo_item(item):
            continue

        if selected_deadlines:
            if ensure_promo_deadline(item) not in selected_deadlines:
                continue

        results.append(item)

    return results


def get_promo_deadlines(items: list[dict[str, Any]]) -> list[str]:
    deadlines: list[str] = []
    seen = set()

    for item in items:
        deadline = ensure_promo_deadline(item)
        if not deadline:
            continue

        if deadline not in seen:
            seen.add(deadline)
            deadlines.append(deadline)

    def sort_key(value: str) -> tuple[int, int]:
        m = re.match(r"^(\d{1,2})/(\d{1,2})$", value)
        if not m:
            return (99, 99)
        return (int(m.group(1)), int(m.group(2)))

    return sorted(deadlines, key=sort_key)


def sort_items_by_price(
    items: list[dict[str, Any]], sort_mode: str
) -> list[dict[str, Any]]:
    if sort_mode == "price_asc":
        return sorted(items, key=lambda item: item.get("price", 0))

    if sort_mode == "price_desc":
        return sorted(items, key=lambda item: item.get("price", 0), reverse=True)

    return items


def group_items_by_promo_deadline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    回傳給模板用：
    [
      {"title": "特價到 6/30", "items": [...]},
      {"title": "特價到 7/15", "items": [...]},
      {"title": "其他特價 / 未標示期限", "items": [...]},
    ]
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    no_deadline: list[dict[str, Any]] = []
    normal: list[dict[str, Any]] = []

    for item in items:
        deadline = ensure_promo_deadline(item)

        if deadline:
            groups.setdefault(deadline, []).append(item)
        elif is_promo_item(item):
            no_deadline.append(item)
        else:
            normal.append(item)

    result: list[dict[str, Any]] = []

    for deadline in get_promo_deadlines(items):
        result.append(
            {
                "title": f"特價到 {deadline}",
                "items": groups.get(deadline, []),
            }
        )

    if no_deadline:
        result.append(
            {
                "title": "其他特價 / 未標示期限",
                "items": no_deadline,
            }
        )

    if normal:
        result.append(
            {
                "title": "一般商品",
                "items": normal,
            }
        )

    return result


def is_probable_product_line(line: str) -> bool:
    if "$" not in line:
        return False

    if "共有商品" in line:
        return False

    if len(line) < 8:
        return False

    return True


def parse_items_from_block(
    block_lines: list[dict[str, str]],
    category_name: str = "",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen = set()

    for row in block_lines:
        line = normalize_spaces(row.get("text", ""))
        group = normalize_spaces(row.get("group", ""))

        if not is_probable_product_line(line):
            continue

        price = extract_price(line)
        if price is None:
            continue

        # 商品名稱去掉價格後面的符號，例如 ◆ ★ 熱賣
        name = re.sub(r"\s*,\s*\$[0-9,]+.*$", "", line).strip()

        if not name:
            continue

        key = (name, price, group)
        if key in seen:
            continue

        seen.add(key)

        items.append(
            {
                "name": name,
                "price": price,
                "category": category_name,
                "group": group,
                "raw": line,
                "promo_deadline": extract_promo_deadline(line),
            }
        )

    return items


def get_category_groups(items: list[dict[str, Any]]) -> list[str]:
    groups: list[str] = []
    seen = set()

    for item in items:
        group = normalize_spaces(item.get("group", ""))
        if not group:
            continue

        if group not in seen:
            seen.add(group)
            groups.append(group)

    return groups


def filter_items_by_group(
    items: list[dict[str, Any]],
    selected_groups: list[str],
) -> list[dict[str, Any]]:
    if not selected_groups:
        return items

    selected = set(selected_groups)

    return [item for item in items if item.get("group", "") in selected]


PLATFORM_FILTER_MODES: dict[str, frozenset[str]] = {
    "cpu_mb": frozenset({"intel", "amd"}),
    "gpu": frozenset({"intel", "nvidia", "amd"}),
}


def get_platform_filter_mode(category_name: str) -> str | None:
    key = normalize_category_key(category_name)
    if key in ("處理器", "主機板"):
        return "cpu_mb"
    if key == "顯示卡":
        return "gpu"
    return None


def supports_platform_filter(category_name: str) -> bool:
    return get_platform_filter_mode(category_name) is not None


def normalize_platform(platform: str, mode: str | None) -> str:
    if not mode:
        return ""

    value = normalize_spaces(platform).lower()
    allowed = PLATFORM_FILTER_MODES.get(mode, frozenset())
    return value if value in allowed else ""


def match_platform_group(group: str, platform: str) -> bool:
    if not platform:
        return True

    label = normalize_spaces(group).lower()
    if platform == "intel":
        return "intel" in label
    if platform == "amd":
        return "amd" in label or "radeon" in label
    if platform == "nvidia":
        return "nvidia" in label or "geforce" in label
    return True


def filter_groups_by_platform(groups: list[str], platform: str) -> list[str]:
    if not platform:
        return groups
    return [g for g in groups if match_platform_group(g, platform)]


def filter_items_by_platform(
    items: list[dict[str, Any]],
    platform: str,
) -> list[dict[str, Any]]:
    if not platform:
        return items
    return [
        item for item in items if match_platform_group(item.get("group", ""), platform)
    ]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("rtx ", "rtx")
    text = text.replace("gtx ", "gtx")
    text = text.replace("rx ", "rx")
    text = text.replace("arc ", "arc")
    text = re.sub(r"\s+", " ", text)
    return text


KNOWN_BRANDS = [
    # 主機板 / 顯卡 / 筆電 / 周邊常見
    "華碩",
    "華擎",
    "技嘉",
    "微星",
    "映泰",
    "精訊",
    "索泰",
    "麗臺",
    "七彩虹",
    "耕宇",
    "撼訊",
    "藍寶",
    "迪蘭",
    "影馳",
    "技鋼",
    "映眾",
    "宏碁",
    "宏碁 Acer",
    "宏碁 predator",
    "acer",
    "asus",
    "asrock",
    "gigabyte",
    "msi",
    "biostar",
    "zotac",
    "leadtek",
    "colorful",
    "galax",
    "gainward",
    "inno3d",
    "powercolor",
    "sapphire",
    # RAM / SSD 常見
    "金士頓",
    "kingston",
    "威剛",
    "adata",
    "美光",
    "micron",
    "crucial",
    "芝奇",
    "g.skill",
    "gskill",
    "十銓",
    "team",
    "teamgroup",
    "t-force",
    "t.create",
    "海盜船",
    "corsair",
    "宇瞻",
    "apacer",
    "創見",
    "transcend",
    "佰維",
    "biwin",
    "umax",
    "klevv",
    "lexar",
    "solidigm",
    "samsung",
    "三星",
    "wd",
    "western digital",
    "威騰",
    "seagate",
    "希捷",
    "sk hynix",
    "hynix",
    "acer predator",
    "predator",
]


SINGLE_SELECT_CATEGORY_FILTERS = frozenset({"支援腳位"})

COOLER_SOCKET_OPTIONS = [
    "115X/1200",
    "AM4/AM5",
    "sTR4/5",
    "1700/1851",
]

COOLER_KEYWORD_SHORTCUTS = [
    "單塔",
    "雙塔",
    "單扇",
    "雙扇",
    "下吹式",
]

COOLER_SOCKET_LETTERS: dict[str, str] = {
    "115x/1200": "W",
    "am4/am5": "X",
    "str4/5": "Y",
    "1700/1851": "Z",
}

CATEGORY_FILTERS: dict[str, dict[str, list[str]]] = {
    "主機板": {
        "板型": [
            "E-ATX",
            "ATX",
            "M-ATX",
            "Micro ATX",
            "Mini-ITX",
            "ITX",
        ],
    },
    "機殼": {
        "支援板型": [
            "E-ATX",
            "ATX",
            "M-ATX",
            "Micro ATX",
            "Mini-ITX",
            "ITX",
        ],
    },
    "散熱器": {
        "支援腳位": COOLER_SOCKET_OPTIONS,
    },
    "水冷": {
        "支援腳位": COOLER_SOCKET_OPTIONS,
    },
    "機殼風扇": {
        "風扇尺寸": [
            "8cm",
            "9cm",
            "12cm",
            "14cm",
            "20cm",
        ],
        "燈效": [
            "ARGB",
            "RGB",
            "無光",
        ],
        "控制": [
            "PWM",
        ],
        "風扇方向": [
            "反葉",
        ],
    },
}


CATEGORY_BRANDS: dict[str, list[str]] = {
    "處理器": ["Intel", "AMD"],
    "主機板": ["華碩", "華擎", "技嘉", "微星", "映泰"],
    "顯示卡": ["華碩", "微星", "技嘉", "撼訊", "藍寶", "索泰", "麗臺"],
    "機殼": ["酷碼", "聯力", "NZXT", "Fractal", "Antec", "曜越", "Montech"],
}


def infer_brands(items: list[dict[str, Any]]) -> list[str]:
    counter = Counter()

    for item in items:
        name_norm = normalize_text(item["name"])
        for brand in KNOWN_BRANDS:
            brand_norm = normalize_text(brand)
            if brand_norm in name_norm:
                counter[brand] += 1

    return [brand for brand, _ in counter.most_common()]


def filter_items(
    items: list[dict[str, Any]],
    keyword: str = "",
    brand: str = "",
) -> list[dict[str, Any]]:
    keyword = normalize_text(keyword)
    brand = normalize_text(brand)
    keyword_parts = keyword.split() if keyword else []

    results = []
    for item in items:
        name = normalize_text(item["name"])

        if brand and brand not in name:
            continue

        if keyword_parts and not all(part in name for part in keyword_parts):
            continue

        results.append(item)

    return results


def matches_white_product(name: str) -> bool:
    if "白" in name:
        return True
    return "white" in name.lower()


def filter_items_by_white(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if matches_white_product(item["name"])]


def choose_price_range() -> tuple[int | None, int | None]:
    print("\n價格篩選")
    print("直接 Enter 表示略過。可輸入數字或含逗號，例如 3,000。")

    def parse_price_input(raw: str) -> int | None:
        raw = raw.strip()
        if not raw:
            return None
        value = raw.replace(",", "")
        if not value.isdigit():
            return -1
        return int(value)

    while True:
        min_raw = input("最低價（可空白）：")
        min_price = parse_price_input(min_raw)
        if min_price == -1:
            print("最低價格式錯誤，請輸入數字。")
            continue

        max_raw = input("最高價（可空白）：")
        max_price = parse_price_input(max_raw)
        if max_price == -1:
            print("最高價格式錯誤，請輸入數字。")
            continue

        if min_price is not None and max_price is not None and min_price > max_price:
            print("最低價不能大於最高價，請重新輸入。")
            continue

        return min_price, max_price


def filter_items_by_price(
    items: list[dict[str, Any]],
    min_price: int | None = None,
    max_price: int | None = None,
) -> list[dict[str, Any]]:
    if min_price is None and max_price is None:
        return items

    results = []
    for item in items:
        price = item["price"]
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        results.append(item)
    return results


def normalize_category_key(category_name: str) -> str:
    name = normalize_spaces(category_name).lower()

    if "處理器" in name or "cpu" in name:
        return "處理器"

    if "主機板" in name:
        return "主機板"

    if "顯示卡" in name or "vga" in name:
        return "顯示卡"

    # 一定要放在「機殼」前面，避免「機殼風扇｜機殼配件」被誤判成機殼
    if "機殼風扇" in name or "機殼配件" in name:
        return "機殼風扇"

    if "電源供應器" in name or ("電源" in name and "機殼" not in name) or "psu" in name:
        return "電源"

    if "case" in name or "機殼" in name:
        return "機殼"

    # 水冷也建議放在散熱器前面
    if "水冷" in name:
        return "水冷"

    if "散熱器" in name or "散熱墊" in name or "散熱膏" in name:
        return "散熱器"

    return ""


def extract_cooler_socket_letters(name: str) -> set[str]:
    match = re.search(r"【([WXYZ]+)】", name, re.IGNORECASE)
    if not match:
        return set()
    return set(match.group(1).upper())


def matches_cooler_socket(name: str, socket_label: str) -> bool:
    letters = extract_cooler_socket_letters(name)
    if not letters:
        return False

    letter = COOLER_SOCKET_LETTERS.get(normalize_text(socket_label), "")
    return letter in letters


GPU_FAN_OPTIONS: list[tuple[str, str]] = [
    ("", "略過"),
    ("0", "無風扇"),
    ("1", "單風扇"),
    ("2", "雙風扇"),
    ("3", "三風扇"),
]

NUMERIC_FILTER_DEFS: dict[str, list[dict[str, Any]]] = {
    "顯示卡": [
        {
            "field": "gpu_length",
            "label": "顯卡長度",
            "type": "max_number",
            "unit_label": "公分 (cm)",
            "placeholder": "例如 30",
            "hint": "依商品名稱標示的顯卡長度篩選，顯示長度 ≤ 此值的商品。",
        },
        {
            "field": "gpu_fans",
            "label": "風扇數量",
            "type": "select",
            "options": GPU_FAN_OPTIONS,
            "hint": "依商品名稱標示的風扇數量精確篩選，可略過。",
        },
    ],
    "機殼": [
        {
            "field": "case_gpu_length",
            "label": "支援顯卡長度",
            "type": "min_number",
            "unit_label": "公分 (cm)",
            "placeholder": "例如 32",
            "hint": "輸入您的顯卡長度，顯示機殼標示「顯卡長」支援值 ≥ 此值的商品。",
        },
        {
            "field": "case_cpu_height",
            "label": "支援 CPU 高度",
            "type": "min_number",
            "unit_label": "公分 (cm)",
            "placeholder": "例如 16",
            "hint": "輸入散熱器高度，顯示機殼標示「CPU高 / U高」支援值 ≥ 此值的商品。",
        },
    ],
    "電源": [
        {
            "field": "psu_wattage",
            "label": "最小瓦數",
            "type": "min_number",
            "unit_label": "瓦 (W)",
            "placeholder": "例如 850",
            "hint": "輸入需求瓦數，顯示商品名稱標示瓦數 ≥ 此值的電源供應器。",
        },
    ],
    "散熱器": [
        {
            "field": "cooler_height",
            "label": "散熱器高度",
            "type": "max_number",
            "unit_label": "公分 (cm)",
            "placeholder": "例如 15.5",
            "hint": "依商品名稱標示的散熱器高度篩選，顯示高度 ≤ 此值的商品。",
        },
    ],
}


def extract_gpu_length_cm(name: str) -> float | None:
    match = re.search(r"/(\d+(?:\.\d+)?)\s*cm", name, re.IGNORECASE)
    if match:
        return float(match.group(1))

    match = re.search(r"(\d+(?:\.\d+)?)\s*cm", name, re.IGNORECASE)
    if match:
        return float(match.group(1))

    return None


def extract_gpu_fan_count(name: str) -> int | None:
    if "無風扇" in name:
        return 0

    for label, count in (("單風扇", 1), ("雙風扇", 2), ("三風扇", 3), ("四風扇", 4)):
        if label in name:
            return count

    match = re.search(r"(\d+)\s*風扇", name)
    if match:
        return int(match.group(1))

    return None


def extract_case_gpu_length_cm(name: str) -> float | None:
    match = re.search(
        r"顯卡長\(?(\d+(?:\.\d+)?)(?:~(\d+(?:\.\d+)?))?\)?",
        name,
    )
    if match:
        low = float(match.group(1))
        high = match.group(2)
        return max(low, float(high)) if high else low

    match = re.search(r"卡長(\d+(?:\.\d+)?)", name)
    if match:
        return float(match.group(1))

    return None


def extract_case_cpu_height_cm(name: str) -> float | None:
    values: list[float] = []
    for pattern in (r"CPU高(\d+(?:\.\d+)?)", r"U高(\d+(?:\.\d+)?)"):
        for match in re.finditer(pattern, name, re.IGNORECASE):
            values.append(float(match.group(1)))

    if not values:
        return None

    return max(values)


def extract_cooler_height_cm(name: str) -> float | None:
    for pattern in (
        r"高(?:度)?(\d+(?:\.\d+)?)\s*cm",
        r"高(\d+(?:\.\d+)?)/",
        r"高(\d+(?:\.\d+)?)【",
        r"高(\d+(?:\.\d+)?)\s",
    ):
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return float(match.group(1))

    return None


def extract_psu_wattage(name: str) -> int | None:
    """
    解析電源供應器瓦數。
    例：
    650W
    750W
    1000W
    1KW
    1.2KW
    """
    match = re.search(r"(\d+(?:\.\d+)?)\s*kw\b", name, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 1000)

    match = re.search(r"(\d{3,4})\s*w\b", name, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


SPEC_EXTRACTORS: dict[str, Any] = {
    "gpu_length": extract_gpu_length_cm,
    "gpu_fans": extract_gpu_fan_count,
    "case_gpu_length": extract_case_gpu_length_cm,
    "case_cpu_height": extract_case_cpu_height_cm,
    "cooler_height": extract_cooler_height_cm,
    "psu_wattage": extract_psu_wattage,
}


NOTEBOOK_CATEGORY_FIELDS: dict[str, list[str]] = {
    "顯示卡": ["gpu_length", "gpu_fans"],
    "機殼": ["case_gpu_length", "case_cpu_height"],
    "電源": ["psu_wattage"],
    "散熱器": ["cooler_height"],
    "水冷": ["cooler_height"],
}


def get_notebook_field_defs() -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    for filters in NUMERIC_FILTER_DEFS.values():
        for fdef in filters:
            field = fdef["field"]
            if field in seen:
                continue
            seen.add(field)
            entry: dict[str, Any] = {
                "field": field,
                "label": fdef["label"],
                "unit": fdef.get("unit_label", ""),
                "type": fdef["type"],
            }
            if fdef["type"] == "select":
                entry["options"] = [
                    {"value": value, "label": label}
                    for value, label in fdef.get("options", [])
                    if value
                ]
            result.append(entry)

    return result


def format_notebook_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def extract_notebook_values(category_name: str, product_name: str) -> dict[str, str]:
    key = normalize_category_key(category_name)
    fields = NOTEBOOK_CATEGORY_FIELDS.get(key, [])
    values: dict[str, str] = {}

    for field in fields:
        extractor = SPEC_EXTRACTORS.get(field)
        if not extractor:
            continue
        raw = extractor(product_name)
        if raw is not None:
            values[field] = format_notebook_value(raw)

    return values


def parse_spec_number(raw: str) -> float | None:
    raw = normalize_spaces(raw).lower().replace(",", "")
    raw = re.sub(r"cm$", "", raw).strip()
    if not raw:
        return None

    try:
        return float(raw)
    except ValueError:
        return None


def get_category_numeric_filters(category_name: str) -> list[dict[str, Any]]:
    key = normalize_category_key(category_name)
    if not key:
        return []
    return NUMERIC_FILTER_DEFS.get(key, [])


def parse_numeric_spec_inputs(
    category_name: str,
    raw_values: dict[str, str],
) -> tuple[dict[str, str], str]:
    selected: dict[str, str] = {}

    for fdef in get_category_numeric_filters(category_name):
        field = fdef["field"]
        raw = raw_values.get(field, "").strip()
        if not raw:
            continue

        if fdef["type"] in ("max_number", "min_number"):
            if parse_spec_number(raw) is None:
                unit = fdef.get("unit_label", "")
                return {}, f"{fdef['label']}格式錯誤，請輸入數字（單位：{unit}）。"
            selected[field] = raw
            continue

        if fdef["type"] == "select":
            valid = {value for value, _ in fdef["options"] if value}
            if raw in valid:
                selected[field] = raw

    return selected, ""


def filter_items_by_numeric_specs(
    items: list[dict[str, Any]],
    spec_values: dict[str, str],
) -> list[dict[str, Any]]:
    if not spec_values:
        return items

    parsed_numbers: dict[str, float] = {}
    parsed_fans: int | None = None

    if "gpu_length" in spec_values:
        value = parse_spec_number(spec_values["gpu_length"])
        if value is not None:
            parsed_numbers["gpu_length"] = value

    if "case_gpu_length" in spec_values:
        value = parse_spec_number(spec_values["case_gpu_length"])
        if value is not None:
            parsed_numbers["case_gpu_length"] = value

    if "case_cpu_height" in spec_values:
        value = parse_spec_number(spec_values["case_cpu_height"])
        if value is not None:
            parsed_numbers["case_cpu_height"] = value

    if "cooler_height" in spec_values:
        value = parse_spec_number(spec_values["cooler_height"])
        if value is not None:
            parsed_numbers["cooler_height"] = value

    if "psu_wattage" in spec_values:
        value = parse_spec_number(spec_values["psu_wattage"])
        if value is not None:
            parsed_numbers["psu_wattage"] = value

    if "gpu_fans" in spec_values:
        parsed_fans = int(spec_values["gpu_fans"])

    if not parsed_numbers and parsed_fans is None:
        return items

    results: list[dict[str, Any]] = []

    for item in items:
        name = item["name"]

        if "gpu_length" in parsed_numbers:
            length = extract_gpu_length_cm(name)
            if length is None or length > parsed_numbers["gpu_length"]:
                continue

        if parsed_fans is not None:
            fans = extract_gpu_fan_count(name)
            if fans is None or fans != parsed_fans:
                continue

        if "case_gpu_length" in parsed_numbers:
            support = extract_case_gpu_length_cm(name)
            if support is None or support < parsed_numbers["case_gpu_length"]:
                continue

        if "case_cpu_height" in parsed_numbers:
            support = extract_case_cpu_height_cm(name)
            if support is None or support < parsed_numbers["case_cpu_height"]:
                continue

        if "cooler_height" in parsed_numbers:
            height = extract_cooler_height_cm(name)
            if height is None or height > parsed_numbers["cooler_height"]:
                continue

        if "psu_wattage" in parsed_numbers:
            wattage = extract_psu_wattage(name)
            if wattage is None or wattage < parsed_numbers["psu_wattage"]:
                continue

        results.append(item)

    return results


def choose_multi_options(title: str, options: list[str]) -> list[str]:
    print(f"\n{title}")
    print("0. 略過")

    for i, opt in enumerate(options, start=1):
        print(f"{i}. {opt}")

    while True:
        raw = input("請輸入編號，可多選（例如 1,2），或輸入 0 略過：").strip()

        if raw == "0":
            return []

        parts = [p.strip() for p in raw.split(",") if p.strip()]
        selected: list[str] = []
        ok = True

        for p in parts:
            if not p.isdigit():
                ok = False
                break

            idx = int(p) - 1
            if not (0 <= idx < len(options)):
                ok = False
                break

            selected.append(options[idx])

        if ok:
            # 去重但保留順序
            result: list[str] = []
            seen = set()
            for x in selected:
                if x not in seen:
                    seen.add(x)
                    result.append(x)
            return result

        print("輸入無效，請重新輸入。")


def get_category_filters(category_name: str) -> dict[str, list[str]]:
    key = normalize_category_key(category_name)
    if not key:
        return {}
    return CATEGORY_FILTERS.get(key, {})


def is_single_select_category_filter(filter_title: str) -> bool:
    return filter_title in SINGLE_SELECT_CATEGORY_FILTERS


def get_category_brands(category_name: str) -> list[str]:
    key = normalize_category_key(category_name)
    if not key:
        return []
    return CATEGORY_BRANDS.get(key, [])


def filter_items_by_category_options(
    items: list[dict[str, Any]],
    selected_filters: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if not selected_filters:
        return items

    def matches_form_factor(name_norm: str, value_norm: str) -> bool:
        if value_norm == "m-atx":
            patterns = [r"\bm[\s\-]?atx\b", r"\bmicro\s*atx\b", r"\bmatx\b"]
            return any(re.search(p, name_norm) for p in patterns)

        if value_norm == "micro atx":
            patterns = [r"\bmicro\s*atx\b", r"\bm[\s\-]?atx\b", r"\bmatx\b"]
            return any(re.search(p, name_norm) for p in patterns)

        if value_norm == "e-atx":
            patterns = [r"\be[\s\-]?atx\b", r"\beatx\b"]
            return any(re.search(p, name_norm) for p in patterns)

        if value_norm == "mini-itx":
            patterns = [r"\bmini[\s\-]?itx\b", r"\bmini itx\b", r"\bitx\b"]
            return any(re.search(p, name_norm) for p in patterns)

        if value_norm == "itx":
            patterns = [r"\bitx\b", r"\bmini[\s\-]?itx\b", r"\bmini itx\b"]
            return any(re.search(p, name_norm) for p in patterns)

        if value_norm == "atx":
            if not re.search(r"\batx\b", name_norm):
                return False
            excludes = [
                r"\bm[\s\-]?atx\b",
                r"\bmicro\s*atx\b",
                r"\bmatx\b",
                r"\be[\s\-]?atx\b",
                r"\beatx\b",
            ]
            return not any(re.search(p, name_norm) for p in excludes)

        return re.search(rf"\b{re.escape(value_norm)}\b", name_norm) is not None

    results = []

    for item in items:
        name = item["name"]
        name_norm = normalize_text(name)
        matched_all_groups = True

        for filter_title, values in selected_filters.items():
            if not values:
                continue

            group_match = False
            for value in values:
                if filter_title == "支援腳位":
                    if matches_cooler_socket(name, value):
                        group_match = True
                        break
                    continue

                if filter_title == "風扇尺寸":
                    if value.lower() in name_norm:
                        group_match = True
                        break
                    continue

                if filter_title == "燈效":
                    if value == "無光":
                        if "argb" not in name_norm and "rgb" not in name_norm:
                            group_match = True
                            break
                    else:
                        if value.lower() in name_norm:
                            group_match = True
                            break
                    continue

                if filter_title == "控制":
                    if value.lower() in name_norm:
                        group_match = True
                        break
                    continue

                if filter_title == "風扇方向":
                    if value in name:
                        group_match = True
                        break
                    continue

                value_norm = normalize_text(value)
                if matches_form_factor(name_norm, value_norm):
                    group_match = True
                    break

            if not group_match:
                matched_all_groups = False
                break

        if matched_all_groups:
            results.append(item)

    return results


def choose_option(
    title: str,
    options: list[str],
    allow_skip: bool = False,
    zero_label: str = "",
) -> str:
    print(f"\n{title}")

    # 計算中英文實際顯示寬度，讓右欄在等寬位置開始
    def display_width(s: str) -> int:
        width = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ("F", "W"):
                width += 2
            else:
                width += 1
        return width

    def pad_to_width(s: str, target: int) -> str:
        cur = display_width(s)
        if cur >= target:
            return s
        return s + " " * (target - cur)

    # 準備所有要顯示的選項字串，之後統一做左右兩欄排版
    lines: list[str] = []

    if zero_label:
        lines.append(f"0. {zero_label}")
    elif allow_skip:
        lines.append("0. 略過")

    for i, opt in enumerate(options, start=1):
        lines.append(f"{i}. {opt}")

    # 計算左欄寬度（以實際顯示寬度為準）
    if lines:
        left_col_width = max(display_width(s) for s in lines)
    else:
        left_col_width = 0

    # 兩欄輸出
    idx = 0
    n = len(lines)
    while idx < n:
        left = lines[idx]
        if idx + 1 < n:
            right = lines[idx + 1]
            print(pad_to_width(left, left_col_width + 4) + right)
            idx += 2
        else:
            print(left)
            idx += 1

    while True:
        raw = input("請輸入編號（或 q 離開）：").strip()

        if raw.lower() == "q":
            print("已結束程式。")
            sys.exit(0)

        if raw == "0":
            if zero_label:
                return "__ZERO__"
            if allow_skip:
                return ""

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]

        print("輸入無效，請重新輸入。")


def print_results(
    results: list[dict[str, Any]],
    limit: int = 1000,
    show_category: bool = False,
) -> None:
    print(f"\n找到 {len(results)} 筆結果：\n")
    for i, item in enumerate(results[:limit], start=1):
        category = item.get("category", "")
        if show_category and category:
            print(f"{i}. [{category}] {item['name']} | ${item['price']:,}")
        else:
            print(f"{i}. {item['name']} | ${item['price']:,}")


def main() -> None:
    try:
        html = fetch_html(URL)
    except Exception as e:
        print(f"[ERROR] 取得頁面失敗：{e}")
        sys.exit(1)

    lines = html_to_lines(html)
    save_debug_files(html, lines)

    category_blocks = build_category_blocks(lines)

    if not category_blocks:
        print("[ERROR] 抓不到分類。")
        print("已輸出 debug 檔案：coolpc_debug_raw.html、coolpc_debug_lines.txt")
        print("請先打開 coolpc_debug_lines.txt，看前 300 行實際長什麼樣。")
        sys.exit(1)

    categories = list(category_blocks.keys())
    category = choose_option(
        "請選擇類別",
        categories,
        allow_skip=False,
        zero_label="全部類別",
    )

    items: list[dict[str, Any]] = []
    brand = ""
    selected_category_filters: dict[str, list[str]] = {}
    min_price: int | None = None
    max_price: int | None = None

    if category == "__ZERO__":
        category_display = "全部類別"

        seen = set()
        for cat_name, block_lines in category_blocks.items():
            block_items = parse_items_from_block(block_lines, category_name=cat_name)
            for item in block_items:
                key = (item["name"], item["price"])
                if key not in seen:
                    seen.add(key)
                    items.append(item)

        if not items:
            print(f"[ERROR] 類別「{category_display}」內抓不到商品。")
            sys.exit(1)

        print("\n已選擇全部類別，將只進行關鍵字搜尋。")

    else:
        category_display = category
        block_lines = category_blocks[category]
        items = parse_items_from_block(block_lines, category_name=category)

        if not items:
            print(f"[ERROR] 類別「{category_display}」內抓不到商品。")
            sys.exit(1)

        category_filter_defs = get_category_filters(category_display)
        if category_filter_defs:
            for filter_title, filter_options in category_filter_defs.items():
                if is_single_select_category_filter(filter_title):
                    picked = choose_option(
                        f"請選擇{filter_title}",
                        filter_options,
                        allow_skip=True,
                    )
                    if picked:
                        selected_category_filters[filter_title] = [picked]
                else:
                    picked = choose_multi_options(
                        f"請選擇{filter_title}", filter_options
                    )
                    if picked:
                        selected_category_filters[filter_title] = picked

            items = filter_items_by_category_options(items, selected_category_filters)

            if not items:
                print(
                    f"[ERROR] 套用分類篩選後，類別「{category_display}」沒有符合商品。"
                )
                sys.exit(1)

        brands = get_category_brands(category_display)
        if not brands:
            brands = infer_brands(items)
        if brands:
            brand = choose_option("請選擇品牌", brands[:20], allow_skip=True)

    min_price, max_price = choose_price_range()
    keyword = input("請輸入關鍵字（可空白）：").strip()
    items = filter_items_by_price(items, min_price=min_price, max_price=max_price)
    results = filter_items(items, keyword=keyword, brand=brand)

    print(f"\n類別：{category_display}")
    if selected_category_filters:
        for filter_title, values in selected_category_filters.items():
            print(f"{filter_title}：{', '.join(values)}")
    if category_display != "全部類別":
        print(f"品牌：{brand or '略過'}")
    if min_price is None and max_price is None:
        print("價格：略過")
    elif min_price is not None and max_price is not None:
        print(f"價格：${min_price:,} ~ ${max_price:,}")
    elif min_price is not None:
        print(f"價格：>= ${min_price:,}")
    else:
        print(f"價格：<= ${max_price:,}")
    print(f"關鍵字：{keyword or '無'}")
    print_results(results, show_category=(category_display == "全部類別"))


if __name__ == "__main__":
    main()
