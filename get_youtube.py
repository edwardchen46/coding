# -*- coding: utf-8 -*-
"""
抓取 YouTube 頻道 @HowHowEat 所有影片標題，並依台灣城市分類到不同資料夾。

技術選型說明：
- 不使用 requests + BeautifulSoup：YouTube 頻道頁是 JavaScript 動態渲染，
  直接抓 HTML 只能拿到前面少數影片。
- 不使用 Selenium：開瀏覽器捲動載入非常耗記憶體且慢。
- 使用 yt-dlp 的 extract_flat 模式：只抓「清單中繼資料」(標題/ID)，
  完全不下載影片，一次 API 呼叫即可取得整個頻道清單，記憶體佔用極低。

安裝依賴：
    pip install yt-dlp
"""

import os
import re
from collections import defaultdict
from typing import Iterator, Tuple

import yt_dlp

# ---------------------------------------------------------------------------
# 路徑安全：以腳本本身位置為基準，cron 或手動執行結果一致
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "titles_by_city")

CHANNEL_URL = "https://www.youtube.com/@HowHowEat/videos"

# 台灣縣市關鍵字（含常見別名/舊稱），value 為正規化後的資料夾名稱
CITY_KEYWORDS = {
    "台北": "台北", "臺北": "台北", "北市": "台北",
    "新北": "新北", "板橋": "新北", "三重": "新北", "淡水": "新北", "永和": "新北", "中和": "新北", "新莊": "新北",
    "基隆": "基隆",
    "桃園": "桃園", "中壢": "桃園",
    "新竹": "新竹", "竹北": "新竹",
    "苗栗": "苗栗",
    "台中": "台中", "臺中": "台中", "逢甲": "台中",
    "彰化": "彰化", "鹿港": "彰化",
    "南投": "南投", "日月潭": "南投", "埔里": "南投",
    "雲林": "雲林", "斗六": "雲林",
    "嘉義": "嘉義",
    "台南": "台南", "臺南": "台南",
    "高雄": "高雄", "左營": "高雄", "旗津": "高雄",
    "屏東": "屏東", "墾丁": "屏東", "恆春": "屏東",
    "宜蘭": "宜蘭", "礁溪": "宜蘭", "羅東": "宜蘭",
    "花蓮": "花蓮",
    "台東": "台東", "臺東": "台東",
    "澎湖": "澎湖",
    "金門": "金門",
    "馬祖": "馬祖",
}

# 預先編譯 regex（長關鍵字優先），避免在迴圈中重複建構 → CPU 效率
_CITY_PATTERN = re.compile(
    "|".join(sorted(map(re.escape, CITY_KEYWORDS), key=len, reverse=True))
)

UNCLASSIFIED = "未分類"


def iter_video_titles(channel_url: str) -> Iterator[Tuple[str, str]]:
    """
    Generator：逐筆 yield (影片標題, 影片網址)。

    為什麼用 yield：
    頻道可能有數千支影片，用 generator 串流處理，
    任何時刻記憶體中只保留一筆資料，而不是整個 list。
    """
    ydl_opts = {
        "extract_flat": "in_playlist",  # 只取清單層級資料，不解析每支影片
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # process=False 讓 entries 以 lazy generator 形式回傳
        info = ydl.extract_info(channel_url, download=False, process=False)
        for entry in info.get("entries", []):
            title = entry.get("title")
            url = entry.get("url", "")
            if title:
                yield title, url


def classify_city(title: str) -> str:
    """回傳標題所屬城市（正規化名稱）；找不到則歸入「未分類」。"""
    match = _CITY_PATTERN.search(title)
    return CITY_KEYWORDS[match.group(0)] if match else UNCLASSIFIED


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 只累積「計數」，標題以 append 模式即時寫入磁碟 → 記憶體 O(城市數) 而非 O(影片數)
    counts = defaultdict(int)
    file_handles = {}

    try:
        for title, url in iter_video_titles(CHANNEL_URL):
            city = classify_city(title)

            if city not in file_handles:
                city_dir = os.path.join(OUTPUT_DIR, city)
                os.makedirs(city_dir, exist_ok=True)
                # 每個城市資料夾內建立 titles.txt，檔案句柄快取重複使用
                file_handles[city] = open(
                    os.path.join(city_dir, "titles.txt"), "w", encoding="utf-8"
                )

            file_handles[city].write(f"{title}\t{url}\n")
            counts[city] += 1
    finally:
        for fh in file_handles.values():
            fh.close()

    # 統計報告
    total = sum(counts.values())
    print(f"完成！共處理 {total} 支影片，輸出目錄：{OUTPUT_DIR}\n")
    for city, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {city}: {n} 支")


if __name__ == "__main__":
    main()