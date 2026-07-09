# -*- coding: utf-8 -*-
"""
mail_sync_script.py
===================
1. 從 Gmail / Yahoo IMAP 增量下載郵件內文與附件 (UID 追蹤)
2. 【新增】掃描 PDF 附件 -> 解密 -> 抽取文字層 -> 判斷是否為信用卡帳單
3. 【新增】若為信用卡帳單,擷取「發卡行 / 應繳金額 / 繳款截止日」
   並透過 Telegram Bot 推送摘要 + PDF 原檔

依賴套件:
    pip install pypdf pymupdf aiohttp
    (pypdf: pdf/ 資料夾解密複製;pymupdf: 帳單文字抽取,未安裝時退回 pypdf 抽取)

設定檔:
    ini/telegram_bot.ini (Bot Token 獨立存放):
        [yoda0217_bot]
        TOKEN = 123456:ABC-DEF...
        ; chat_id 可放這裡,也可放 mail.ini 的 [telegram] 區塊
        chat_id = 123456789

    ini/passwd.txt (PDF 解密密碼,一行一組,# 開頭為註解):
        A123456789
        19800101

    ini/mail.ini 需新增區塊 (程式會自動補範本):
        [telegram]
        chat_id = 123456789
"""

import os
import re
import sys
import time
import email
import email.message
import email.utils
import imaplib
import shutil
import asyncio
import logging
import configparser
from dataclasses import dataclass, field
from typing import Optional, Iterator
from email.header import decode_header
from datetime import datetime

# --- 選配依賴:缺少時不中斷收信主流程,僅停用帳單辨識/推送功能 -------------
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from pypdf import PdfReader, PdfWriter
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

# ---------------------------------------------------------------------------
# 全域常數
# ---------------------------------------------------------------------------

# 1. 絕對路徑鎖定:無論從哪個工作目錄呼叫,都以「程式檔案自身」的所在資料夾為基準
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INI_DIR = os.path.join(BASE_DIR, "ini")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
PDF_DIR = os.path.join(BASE_DIR, "pdf")  # PDF 集中資料夾 (解密版/複本)
ELECTRONIC_BILL_DIR = os.path.join(BASE_DIR, "electronic_bill")  # 電子帳單集中資料夾

MAIL_INI_PATH = os.path.join(INI_DIR, "mail.ini")

# Telegram Bot Token 獨立設定檔 (與其他 Bot 專案共用同一份)
TELEGRAM_INI_PATH = os.path.join(INI_DIR, "telegram_bot.ini")
TELEGRAM_BOT_SECTION = "yoda0217_bot"

# PDF 解密密碼檔:一行一組密碼 (# 開頭視為註解)
PASSWD_TXT_PATH = os.path.join(INI_DIR, "passwd.txt")

LOG_RETENTION_DAYS = 30
FILENAME_BYTE_LIMIT = 130  # 主旨/附件主檔名的位元組上限

IMAP_SERVERS = {
    "google_mail": {"provider": "Google", "host": "imap.gmail.com", "port": 993},
    "yahoo_mail": {"provider": "Yahoo", "host": "imap.mail.yahoo.com", "port": 993},
}

# Windows/Linux 檔名不允許的符號
_INVALID_FS_CHARS = r'\\/:*?"<>|'

# ---------------------------------------------------------------------------
# 【新增】信用卡帳單辨識常數
# ---------------------------------------------------------------------------

# 只解析前 N 頁:帳單關鍵資訊(金額/截止日)一定在首頁,
# 避免整份 PDF 全部載入解析浪費記憶體與 CPU
PDF_SCAN_MAX_PAGES = 3

# 判斷規則:必須命中「主關鍵字」至少 1 個,且「輔助關鍵字」至少 2 個,
# 雙門檻可避免一般行銷信 (內文提到"信用卡優惠") 被誤判成帳單
BILL_PRIMARY_KEYWORDS = ("信用卡", "卡友")
BILL_SECONDARY_KEYWORDS = (
    "本期應繳", "應繳金額", "應繳總金額", "繳款截止", "繳款期限",
    "最低應繳", "循環信用", "結帳日", "電子帳單", "本期新增款項",
)

# 台灣主要發卡行 (供摘要顯示,比對不到不影響帳單判定)
TW_BANK_NAMES = (
    "台新", "國泰世華", "中國信託", "玉山", "台北富邦", "富邦",
    "花旗", "聯邦", "永豐", "兆豐", "第一銀行", "華南", "彰化銀行",
    "上海商業儲蓄", "渣打", "匯豐", "樂天", "星展", "遠東商銀",
    "王道", "凱基", "新光", "陽信", "合作金庫", "土地銀行", "郵局",
)

# --- 通用電子帳單 (電費/水費/電信/瓦斯/稅費...) 辨識常數 ---

# 通用帳單關鍵字:命中 >= 2 個即視為電子帳單
EBILL_KEYWORDS = (
    "電子帳單", "繳費通知", "帳單金額", "應繳金額", "繳費期限",
    "繳款期限", "本期應繳", "繳款截止", "繳費金額", "代收截止",
)

# 帳單類型判斷規則 (依序比對,先中先贏)
EBILL_TYPE_RULES = (
    ("信用卡", "信用卡帳單"),
    ("台灣電力", "電費帳單"), ("電費", "電費帳單"),
    ("自來水", "水費帳單"), ("水費", "水費帳單"),
    ("天然氣", "瓦斯帳單"), ("瓦斯", "瓦斯帳單"),
    ("中華電信", "電信帳單"), ("台灣大哥大", "電信帳單"),
    ("遠傳", "電信帳單"), ("電信費", "電信帳單"),
    ("健保", "健保費帳單"), ("國民年金", "國民年金帳單"),
    ("燃料費", "汽機車燃料費"), ("牌照稅", "稅費帳單"),
    ("房屋稅", "稅費帳單"), ("地價稅", "稅費帳單"), ("所得稅", "稅費帳單"),
)

# 常見發單機構 (供摘要顯示)
EBILL_ISSUERS = (
    "台灣電力", "台灣自來水", "臺北自來水", "中華電信", "台灣大哥大",
    "遠傳電信", "遠傳", "大台北瓦斯", "欣欣天然氣", "欣中天然氣",
    "衛生福利部中央健康保險署", "健保署", "財政部", "國稅局", "監理",
)

# 金額/日期擷取正則 (預先編譯,避免每封信重複編譯)
_RE_AMOUNT_DUE = re.compile(
    r"(?:本期應繳(?:總?金額)?|應繳總?金額|本期應付(?:總?金額)?)"
    r"[^\d\-]{0,25}?([\d,]{1,15})"
)
_RE_MIN_PAYMENT = re.compile(r"最低應繳(?:金額)?[^\d\-]{0,25}?([\d,]{1,15})")
_RE_DUE_DATE = re.compile(
    r"(?:繳款截止日|繳款期限|繳費期限|最後繳款日)"
    r"[^\d]{0,15}?(\d{2,4}\s*[./年-]\s*\d{1,2}\s*[./月-]\s*\d{1,2}\s*日?)"
)

TELEGRAM_API_BASE = "https://api.telegram.org"


# ---------------------------------------------------------------------------
# 【新增】帳單資料結構
# ---------------------------------------------------------------------------

@dataclass
class CardBill:
    """單筆帳單辨識結果 (信用卡或通用電子帳單),供 Telegram 推送使用。"""
    pdf_path: str
    account: str                       # 收信帳號 (哪個信箱收到的)
    bill_type: str = "信用卡帳單"      # 信用卡帳單 / 電費帳單 / 水費帳單 ...
    mail_subject: str = ""
    mail_from: str = ""
    bank: str = ""                     # 發卡行 (比對不到則空字串)
    amount_due: str = ""               # 本期應繳金額
    min_payment: str = ""              # 最低應繳金額
    due_date: str = ""                 # 繳款截止日
    was_encrypted: bool = False        # 原始 PDF 是否加密
    is_decrypted_copy: bool = False    # 推送的檔案是否為已解密版本
    matched_keywords: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 日誌 (Logging) 設定
# ---------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    """建立 logs/ 目錄、設定雙輸出 (終端機 + 當日 log 檔),並清理逾 30 天的舊 log。"""
    os.makedirs(LOGS_DIR, exist_ok=True)

    today_str = datetime.now().strftime("%Y%m%d")
    log_file_path = os.path.join(LOGS_DIR, f"{today_str}.logs")

    logger = logging.getLogger("EmailDownloader")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # 避免重複執行時 handler 疊加

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 終端機輸出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 檔案輸出 (utf-8)
    file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    cleanup_old_logs(logger)
    return logger


def cleanup_old_logs(logger: logging.Logger) -> None:
    """掃描 logs/ 資料夾,將超過 LOG_RETENTION_DAYS 天的舊日誌實體刪除。"""
    cutoff_time = time.time() - (LOG_RETENTION_DAYS * 86400)

    try:
        entries = os.listdir(LOGS_DIR)
    except Exception as exc:
        logger.warning("無法掃描 logs 資料夾以清理舊日誌: %s", exc)
        return

    for filename in entries:
        file_path = os.path.join(LOGS_DIR, filename)
        try:
            if not os.path.isfile(file_path):
                continue
            mtime = os.path.getmtime(file_path)
            if mtime < cutoff_time:
                os.remove(file_path)
                logger.info("已清理逾 %d 天的舊日誌: %s", LOG_RETENTION_DAYS, filename)
        except Exception as exc:
            # 個別檔案鎖定/權限問題不應中斷整體清理流程
            logger.warning("清理日誌檔案 %s 時發生例外,已略過: %s", filename, exc)
            continue


# ---------------------------------------------------------------------------
# 字元清洗 / 安全檔名處理
# ---------------------------------------------------------------------------

def decode_mime_words(raw_value: str) -> str:
    """使用 decode_header 將主旨/寄件者/附件名稱等 MIME 編碼字串還原為可讀文字。"""
    if not raw_value:
        return ""
    try:
        decoded_parts = decode_header(raw_value)
        result_segments = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result_segments.append(part.decode(charset or "utf-8", errors="ignore"))
                except (LookupError, UnicodeDecodeError):
                    result_segments.append(part.decode("utf-8", errors="ignore"))
            else:
                result_segments.append(part)
        return "".join(result_segments)
    except Exception:
        return str(raw_value)


def sanitize_filename_chars(raw_name: str) -> str:
    """
    嚴格清洗檔名字元:
        - 移除 Windows/Linux 不允許的符號: \\ / : * ? " < > |
        - 移除 \t (Tab) 以及所有不可見的 ASCII 控制字元 (0x00-0x1F, 0x7F)
        - 移除頭尾多餘空白
    防止 Windows 因不合法字元拋出 Errno 22 (Invalid argument)。
    """
    if not raw_name:
        return "untitled"

    # 移除常見不合法符號
    cleaned = re.sub(f"[{re.escape(_INVALID_FS_CHARS)}]", "_", raw_name)

    # 移除所有 ASCII 控制字元 (含 \t \n \r 以及其他不可見字元 0x00-0x1F, 0x7F)
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32 and ord(ch) != 127)

    cleaned = cleaned.strip()
    return cleaned if cleaned else "untitled"


def truncate_by_bytes(text: str, max_bytes: int = FILENAME_BYTE_LIMIT) -> str:
    """
    依「位元組」而非「字元數」截斷字串,避免中文 (UTF-8 佔 3 bytes)
    或 Emoji (佔 4 bytes) 被硬切成無法解碼的殘片。
    使用 errors='ignore' 讓截斷點落在多位元組字元中間時,直接捨棄該不完整字元。
    """
    if text is None:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated_bytes = encoded[:max_bytes]
    return truncated_bytes.decode("utf-8", errors="ignore")


def build_safe_basename(raw_name: str) -> str:
    """整合清洗 + 位元組截斷,回傳可安全使用於檔名的基底字串。"""
    cleaned = sanitize_filename_chars(raw_name)
    return truncate_by_bytes(cleaned, FILENAME_BYTE_LIMIT)


# ---------------------------------------------------------------------------
# 【新增】PDF 文字抽取 + 信用卡帳單辨識
# ---------------------------------------------------------------------------

def iter_pdf_page_text(doc: "fitz.Document",
                       max_pages: int = PDF_SCAN_MAX_PAGES) -> Iterator[str]:
    """
    以 Generator 逐頁產出文字。

    為什麼用 yield:帳單判定通常在第 1 頁就能完成,Generator 讓呼叫端
    可以「邊讀邊判斷、提早停止」,不必一次把整份 PDF 的文字全部載入記憶體
    (部分銀行帳單附帶數十頁的消費明細與廣告頁)。
    """
    page_limit = min(len(doc), max_pages)
    for page_index in range(page_limit):
        yield doc[page_index].get_text("text")


def extract_pdf_text(pdf_path: str, passwords: tuple,
                     logger: logging.Logger) -> tuple:
    """
    開啟 PDF -> 若加密則依序嘗試密碼 -> 抽取前 N 頁文字層。

    回傳 (text, was_encrypted):
        text = None  -> 加密且所有密碼都失敗,或檔案損毀
        text = ""    -> 開啟成功但沒有文字層 (掃描圖片型 PDF)

    優先用 PyMuPDF (中文抽取品質較佳);未安裝時退回 pypdf。
    """
    if fitz is None:
        if _PYPDF_AVAILABLE:
            return _extract_pdf_text_pypdf(pdf_path, passwords, logger)
        logger.warning("未安裝 PyMuPDF 或 pypdf,無法抽取 PDF 文字,跳過辨識。")
        return None, False

    doc = None
    try:
        doc = fitz.open(pdf_path)
        was_encrypted = bool(doc.needs_pass)

        if was_encrypted:
            # 依序嘗試設定檔中的密碼 (身分證字號/生日等)
            for pw in passwords:
                if doc.authenticate(pw):
                    logger.debug("PDF 解密成功: %s", os.path.basename(pdf_path))
                    break
            else:
                logger.warning("PDF 已加密且所有密碼皆失敗: %s",
                               os.path.basename(pdf_path))
                return None, True

        # Generator 逐頁累積;提前偵測到足夠內容即可停止
        collected_parts = []
        for page_text in iter_pdf_page_text(doc):
            collected_parts.append(page_text)
        return "\n".join(collected_parts), was_encrypted

    except Exception as exc:
        logger.error("解析 PDF %s 失敗: %s", os.path.basename(pdf_path), exc)
        return None, False
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


def _extract_pdf_text_pypdf(pdf_path: str, passwords: tuple,
                            logger: logging.Logger) -> tuple:
    """pypdf 備援文字抽取:介面與 extract_pdf_text 相同。"""
    try:
        reader = PdfReader(pdf_path)
        was_encrypted = bool(reader.is_encrypted)

        if was_encrypted:
            for pw in passwords:
                try:
                    if reader.decrypt(pw):
                        break
                except Exception:
                    continue
            else:
                logger.warning("PDF 已加密且所有密碼皆失敗 (pypdf): %s",
                               os.path.basename(pdf_path))
                return None, True

        # Generator 運算式逐頁抽取,只取前 N 頁避免整份載入
        page_limit = min(len(reader.pages), PDF_SCAN_MAX_PAGES)
        text = "\n".join(
            (reader.pages[i].extract_text() or "") for i in range(page_limit)
        )
        return text, was_encrypted
    except Exception as exc:
        logger.error("解析 PDF %s 失敗 (pypdf): %s",
                     os.path.basename(pdf_path), exc)
        return None, False


def analyze_credit_card_bill(text: str) -> Optional[dict]:
    """
    以「雙門檻關鍵字」判斷文字內容是否為信用卡帳單;
    是 -> 回傳擷取欄位 dict,否 -> 回傳 None。

    採規則式判斷而非 AI/視覺模型的原因:
        台灣電子帳單 PDF 幾乎都有文字層,規則式毫秒級完成、零成本、可離線,
        視覺辨識留作未來掃描檔的備援即可。
    """
    if not text:
        return None

    primary_hits = [kw for kw in BILL_PRIMARY_KEYWORDS if kw in text]
    secondary_hits = [kw for kw in BILL_SECONDARY_KEYWORDS if kw in text]

    # 雙門檻:主關鍵字 >= 1 且輔助關鍵字 >= 2,降低行銷信誤判
    if not primary_hits or len(secondary_hits) < 2:
        return None

    bank = next((name for name in TW_BANK_NAMES if name in text), "")

    amount_match = _RE_AMOUNT_DUE.search(text)
    min_match = _RE_MIN_PAYMENT.search(text)
    due_match = _RE_DUE_DATE.search(text)

    return {
        "bank": bank,
        "amount_due": amount_match.group(1) if amount_match else "",
        "min_payment": min_match.group(1) if min_match else "",
        "due_date": re.sub(r"\s+", "", due_match.group(1)) if due_match else "",
        "matched_keywords": primary_hits + secondary_hits,
    }


# 通用電子帳單的金額/期限正則 (涵蓋非信用卡帳單常見寫法)
_RE_EBILL_AMOUNT = re.compile(
    r"(?:應繳(?:總?金額)?|帳單金額|繳費金額|本期費用)[^\d\-]{0,25}?([\d,]{1,15})"
)
_RE_EBILL_DUE = re.compile(
    r"(?:繳費期限|繳款期限|繳費截止|繳款截止日?|代收截止)"
    r"[^\d]{0,15}?(\d{2,4}\s*[./年-]\s*\d{1,2}\s*[./月-]\s*\d{1,2}\s*日?)"
)


def analyze_electronic_bill(text: str) -> Optional[dict]:
    """
    通用電子帳單判斷 (電費/水費/電信/瓦斯/稅費...):
    命中 EBILL_KEYWORDS >= 2 個即視為電子帳單,並嘗試判斷類型與擷取欄位。
    信用卡帳單請先用 analyze_credit_card_bill() 判斷 (訊息格式較豐富),
    此函式作為第二層的通用網。
    """
    if not text:
        return None

    keyword_hits = [kw for kw in EBILL_KEYWORDS if kw in text]
    if len(keyword_hits) < 2:
        return None

    bill_type = next(
        (label for kw, label in EBILL_TYPE_RULES if kw in text), "電子帳單")
    issuer = next(
        (name for name in EBILL_ISSUERS + TW_BANK_NAMES if name in text), "")

    amount_match = _RE_EBILL_AMOUNT.search(text)
    due_match = _RE_EBILL_DUE.search(text)

    return {
        "bill_type": bill_type,
        "issuer": issuer,
        "amount_due": amount_match.group(1) if amount_match else "",
        "due_date": re.sub(r"\s+", "", due_match.group(1)) if due_match else "",
        "matched_keywords": keyword_hits,
    }


# ---------------------------------------------------------------------------
# 【新增】Telegram 非同步推送
# ---------------------------------------------------------------------------

def _format_bill_message(bill: CardBill) -> str:
    """組合 Telegram 推送文字 (HTML parse mode);信用卡與通用電子帳單格式不同。"""
    if bill.bill_type == "信用卡帳單":
        lines = ["💳 <b>偵測到信用卡繳費帳單</b>", ""]
        if bill.bank:
            lines.append(f"🏦 發卡行:<b>{bill.bank}</b>")
        if bill.amount_due:
            lines.append(f"💰 本期應繳:<b>NT$ {bill.amount_due}</b>")
        if bill.min_payment:
            lines.append(f"🔻 最低應繳:NT$ {bill.min_payment}")
        if bill.due_date:
            lines.append(f"⏰ 繳款截止:<b>{bill.due_date}</b>")
    else:
        lines = ["📄 <b>偵測到電子帳單</b>", ""]
        lines.append(f"🧾 類型:<b>{bill.bill_type}</b>")
        if bill.bank:
            lines.append(f"🏢 機構:{bill.bank}")
        if bill.amount_due:
            lines.append(f"💰 應繳金額:<b>NT$ {bill.amount_due}</b>")
        if bill.due_date:
            lines.append(f"⏰ 繳費期限:<b>{bill.due_date}</b>")
    lines.append("")
    lines.append(f"📧 收件信箱:{bill.account}")
    if bill.mail_subject:
        lines.append(f"✉️ 郵件主旨:{bill.mail_subject}")
    if bill.was_encrypted and bill.is_decrypted_copy:
        lines.append("🔓 原始 PDF 有密碼,附上的是已解密版本,直接開啟即可")
    elif bill.was_encrypted:
        lines.append("🔒 PDF 有密碼保護,開啟附件請輸入你的帳單密碼")
    return "\n".join(lines)


async def _push_single_bill(session: "aiohttp.ClientSession", bot_token: str,
                            chat_id: str, bill: CardBill,
                            logger: logging.Logger) -> None:
    """推送單筆帳單:先發文字摘要,再傳 PDF 原檔。"""
    base = f"{TELEGRAM_API_BASE}/bot{bot_token}"

    # 1) 文字摘要
    async with session.post(f"{base}/sendMessage", json={
        "chat_id": chat_id,
        "text": _format_bill_message(bill),
        "parse_mode": "HTML",
    }) as resp:
        if resp.status != 200:
            logger.error("Telegram sendMessage 失敗 (HTTP %s): %s",
                         resp.status, await resp.text())

    # 2) PDF 原檔 — 傳入檔案物件由 aiohttp 串流上傳,不一次讀進記憶體
    try:
        with open(bill.pdf_path, "rb") as pdf_file:
            form = aiohttp.FormData()
            form.add_field("chat_id", str(chat_id))
            form.add_field("document", pdf_file,
                           filename=os.path.basename(bill.pdf_path),
                           content_type="application/pdf")
            async with session.post(f"{base}/sendDocument", data=form) as resp:
                if resp.status != 200:
                    logger.error("Telegram sendDocument 失敗 (HTTP %s): %s",
                                 resp.status, await resp.text())
                else:
                    logger.info("Telegram 已推送帳單: %s",
                                os.path.basename(bill.pdf_path))
    except FileNotFoundError:
        logger.error("推送時找不到 PDF 檔案: %s", bill.pdf_path)


async def push_bills_async(bot_token: str, chat_id: str, bills: list,
                           logger: logging.Logger) -> None:
    """
    使用 aiohttp 併發推送所有帳單。

    為什麼用 asyncio + gather:推送屬於 Network-Bound 工作,
    多張帳單同時上傳可將總耗時從「逐筆相加」壓縮為「最慢一筆」。
    """
    timeout = aiohttp.ClientTimeout(total=120)  # PDF 上傳較耗時,放寬逾時
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            *(_push_single_bill(session, bot_token, chat_id, b, logger)
              for b in bills),
            return_exceptions=True,
        )
    for bill, result in zip(bills, results):
        if isinstance(result, Exception):
            logger.error("推送 %s 時發生例外: %s",
                         os.path.basename(bill.pdf_path), result)


# ---------------------------------------------------------------------------
# EmailDownloader 主類別
# ---------------------------------------------------------------------------

class EmailDownloader:
    """
    負責讀取設定檔、連線 IMAP 伺服器、比對 UID 增量下載郵件內文與附件,
    並將結果依日期歸檔至本地端資料夾。
    【新增】掃描 PDF 附件辨識信用卡帳單,收集後統一併發推送 Telegram。
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.config = configparser.ConfigParser()

        # 確保基礎資料夾存在 (ini/ downloads/ pdf/ 皆鎖定在程式檔案旁)
        os.makedirs(INI_DIR, exist_ok=True)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(PDF_DIR, exist_ok=True)
        os.makedirs(ELECTRONIC_BILL_DIR, exist_ok=True)

        self._load_config()

        # --- 【新增】Telegram 與 PDF 密碼設定 ---
        self.tg_bot_token, self.tg_chat_id = self._load_telegram_config()
        self.pdf_passwords = self._load_pdf_passwords()

        # 本輪執行偵測到的帳單,run() 結尾統一併發推送
        self.pending_bills: list = []

        if not self.tg_bot_token or not self.tg_chat_id:
            self.logger.warning(
                "Telegram TOKEN/chat_id 未設定,帳單只會辨識記錄、不會推送。")

    def _load_telegram_config(self) -> tuple:
        """
        讀取 Telegram 設定:
            TOKEN   -> ini/telegram_bot.ini 的 [yoda0217_bot] 區塊 (TOKEN=)
            chat_id -> 優先讀同區塊的 chat_id;沒有再退回 mail.ini 的 [telegram] 區塊
        Token 獨立成檔的好處:多支 Bot 程式可共用同一份憑證,換 Token 只改一處。
        """
        token = ""
        chat_id = ""

        if os.path.isfile(TELEGRAM_INI_PATH):
            tg_config = configparser.ConfigParser()
            try:
                tg_config.read(TELEGRAM_INI_PATH, encoding="utf-8")
                if tg_config.has_section(TELEGRAM_BOT_SECTION):
                    # configparser 的 key 不分大小寫,TOKEN= 會以 token 讀取
                    token = tg_config.get(TELEGRAM_BOT_SECTION, "TOKEN",
                                          fallback="").strip()
                    chat_id = tg_config.get(TELEGRAM_BOT_SECTION, "chat_id",
                                            fallback="").strip()
                else:
                    self.logger.warning(
                        "%s 缺少區塊 [%s],無法讀取 Bot Token。",
                        TELEGRAM_INI_PATH, TELEGRAM_BOT_SECTION)
            except Exception as exc:
                self.logger.error("讀取 %s 失敗: %s", TELEGRAM_INI_PATH, exc)
        else:
            self.logger.warning("找不到 Telegram 設定檔: %s", TELEGRAM_INI_PATH)

        # chat_id 備援:mail.ini 的 [telegram] 區塊
        if not chat_id:
            chat_id = self.config.get("telegram", "chat_id", fallback="").strip()

        return token, chat_id

    def _load_pdf_passwords(self) -> tuple:
        """
        讀取 PDF 解密密碼,優先順序:
            1. ini/passwd.txt — 一行一組密碼,空行與 # 開頭的註解行略過
            2. (備援) mail.ini 的 [pdf] passwords,逗號分隔
        解密時會依「檔案內的行序」逐一嘗試,常用密碼放最上面可加快解密。
        """
        passwords = []

        if os.path.isfile(PASSWD_TXT_PATH):
            try:
                with open(PASSWD_TXT_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        pw = line.strip()
                        if pw and not pw.startswith("#"):
                            passwords.append(pw)
                self.logger.info("已從 %s 載入 %d 組 PDF 密碼。",
                                 PASSWD_TXT_PATH, len(passwords))
            except Exception as exc:
                self.logger.error("讀取密碼檔 %s 失敗: %s", PASSWD_TXT_PATH, exc)
        else:
            self.logger.warning("找不到 PDF 密碼檔: %s", PASSWD_TXT_PATH)

        # 備援:mail.ini 的 [pdf] passwords (逗號分隔)
        if not passwords:
            raw = self.config.get("pdf", "passwords", fallback="").strip()
            passwords = [pw.strip() for pw in raw.split(",") if pw.strip()]

        # dict.fromkeys 去除重複密碼但保留原始順序
        return tuple(dict.fromkeys(passwords))

    # ------------------------------------------------------------------
    # 設定檔讀取
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        if not os.path.isfile(MAIL_INI_PATH):
            self.logger.error(
                "找不到設定檔 %s,請先建立 ini/mail.ini 並填入 [google_mail]/[yahoo_mail] 帳密。",
                MAIL_INI_PATH,
            )
            self._create_template_ini_if_missing()
            raise FileNotFoundError(f"設定檔不存在: {MAIL_INI_PATH}")

        self.config.read(MAIL_INI_PATH, encoding="utf-8")
        self.logger.info("已成功讀取設定檔: %s", MAIL_INI_PATH)

    def _create_template_ini_if_missing(self) -> None:
        """若 mail.ini 不存在,自動產生一份範本方便使用者填寫,並提早結束避免用空帳密連線。"""
        try:
            template = configparser.ConfigParser()
            template["google_mail"] = {"username": "", "password": ""}
            template["yahoo_mail"] = {"username": "", "password": ""}
            # 【新增】Telegram chat_id 與 PDF 密碼範本區塊
            # (Bot Token 放在獨立的 ini/telegram_bot.ini)
            template["telegram"] = {"chat_id": ""}
            template["pdf"] = {"passwords": ""}
            with open(MAIL_INI_PATH, "w", encoding="utf-8") as f:
                template.write(f)
            self.logger.info("已建立範本設定檔,請填寫後再次執行: %s", MAIL_INI_PATH)
        except Exception as exc:
            self.logger.error("建立範本設定檔失敗: %s", exc)

    # ------------------------------------------------------------------
    # UID 追蹤檔 (增量下載機制)
    # ------------------------------------------------------------------
    def _uid_tracker_path(self, provider: str, account: str) -> str:
        safe_account = sanitize_filename_chars(account)
        return os.path.join(INI_DIR, f"{provider}_{safe_account}_uids.txt")

    def _load_known_uids(self, tracker_path: str) -> set:
        known = set()
        if os.path.isfile(tracker_path):
            try:
                with open(tracker_path, "r", encoding="utf-8") as f:
                    for line in f:
                        uid = line.strip()
                        if uid:
                            known.add(uid)
            except Exception as exc:
                self.logger.warning("讀取 UID 追蹤檔 %s 失敗: %s", tracker_path, exc)
        return known

    def _append_uid(self, tracker_path: str, uid: str) -> None:
        """每成功處理完一封信,立即 append 寫入追蹤檔,避免排程中斷造成漏信或重複下載。"""
        try:
            with open(tracker_path, "a", encoding="utf-8") as f:
                f.write(f"{uid}\n")
        except Exception as exc:
            self.logger.error("寫入 UID 追蹤檔 %s 失敗 (uid=%s): %s", tracker_path, uid, exc)

    # ------------------------------------------------------------------
    # 主流程:對每個帳號區塊依序處理
    # ------------------------------------------------------------------
    def run(self) -> None:
        for section, server_info in IMAP_SERVERS.items():
            if not self.config.has_section(section):
                self.logger.warning("設定檔缺少區塊 [%s],略過。", section)
                continue

            username = self.config.get(section, "username", fallback="").strip()
            password = self.config.get(section, "password", fallback="").strip()

            if not username or not password:
                self.logger.warning("[%s] 帳號或密碼為空,略過此帳號。", section)
                continue

            provider = server_info["provider"]
            self.logger.info("=== 開始處理帳號 [%s] provider=%s ===", username, provider)

            try:
                self._process_account(provider, server_info["host"], server_info["port"],
                                      username, password)
            except imaplib.IMAP4.error as imap_exc:
                self.logger.error("[%s] IMAP 連線/驗證失敗: %s", username, imap_exc)
            except Exception as exc:
                # 確保單一帳號的任何非預期錯誤都不會中斷整支程式
                self.logger.exception("[%s] 處理過程發生未預期錯誤: %s", username, exc)

        # --- 【新增】所有帳號處理完畢後,統一併發推送本輪偵測到的帳單 ---
        self._push_pending_bills()

    def _push_pending_bills(self) -> None:
        """run() 收尾:將本輪偵測到的信用卡帳單透過 Telegram 併發推送。"""
        if not self.pending_bills:
            self.logger.info("本輪未偵測到信用卡帳單。")
            return

        self.logger.info("本輪共偵測到 %d 份信用卡帳單。", len(self.pending_bills))

        if not self.tg_bot_token or not self.tg_chat_id:
            self.logger.warning("Telegram 未設定,略過推送。")
            return
        if aiohttp is None:
            self.logger.error("未安裝 aiohttp (pip install aiohttp),無法推送 Telegram。")
            return

        try:
            asyncio.run(push_bills_async(
                self.tg_bot_token, self.tg_chat_id,
                self.pending_bills, self.logger,
            ))
        except Exception as exc:
            self.logger.exception("Telegram 推送流程發生例外: %s", exc)

    # ------------------------------------------------------------------
    # 單一帳號處理:連線 -> 抓取新 UID -> 逐封下載 -> 歸檔
    # ------------------------------------------------------------------
    def _process_account(self, provider: str, host: str, port: int,
                         username: str, password: str) -> None:
        tracker_path = self._uid_tracker_path(provider, username)
        known_uids = self._load_known_uids(tracker_path)
        self.logger.info("[%s] 目前已記錄 %d 筆 UID。", username, len(known_uids))

        imap_conn = imaplib.IMAP4_SSL(host, port)
        try:
            imap_conn.login(username, password)
            imap_conn.select("INBOX")

            status, uid_data = imap_conn.uid("search", None, "ALL")
            if status != "OK":
                self.logger.error("[%s] UID search 失敗: %s", username, status)
                return

            all_uids = uid_data[0].split() if uid_data and uid_data[0] else []
            new_uids = [uid.decode() for uid in all_uids if uid.decode() not in known_uids]

            self.logger.info("[%s] 共 %d 封信,新增 %d 封待下載。",
                             username, len(all_uids), len(new_uids))

            for uid_str in new_uids:
                try:
                    self._download_single_mail(imap_conn, provider, username, uid_str)
                    # 每成功處理完一封信,立即寫入追蹤檔,避免中途中斷造成漏信或重複下載
                    self._append_uid(tracker_path, uid_str)
                except Exception as mail_exc:
                    self.logger.exception(
                        "[%s] 處理 UID=%s 時發生錯誤,跳過此封信 (不寫入追蹤檔,下次會重試): %s",
                        username, uid_str, mail_exc,
                    )
        finally:
            try:
                imap_conn.logout()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 下載單一封信 (內文 + 附件),並依日期歸檔
    # ------------------------------------------------------------------
    def _download_single_mail(self, imap_conn: imaplib.IMAP4_SSL, provider: str,
                              username: str, uid_str: str) -> None:
        status, msg_data = imap_conn.uid("fetch", uid_str, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            self.logger.warning("[%s] UID=%s fetch 失敗,跳過。", username, uid_str)
            return

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_words(msg.get("Subject", ""))
        from_addr = decode_mime_words(msg.get("From", ""))
        date_header = msg.get("Date", "")

        received_dt = self._parse_email_date(date_header)

        account_prefix = username.split("@")[0]
        day_dir = os.path.join(
            DOWNLOADS_DIR,
            provider,
            sanitize_filename_chars(account_prefix),
            received_dt.strftime("%Y"),
            received_dt.strftime("%m"),
            received_dt.strftime("%d"),
        )
        os.makedirs(day_dir, exist_ok=True)

        safe_subject_base = build_safe_basename(subject) if subject else "no_subject"
        timestamp_str = received_dt.strftime("%Y%m%d_%H%M%S")

        # 純文字內文
        body_text = self._extract_plain_text_body(msg)
        text_filename = f"{uid_str}_text_{timestamp_str}_{safe_subject_base}.txt"
        text_path = os.path.join(day_dir, text_filename)

        try:
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(f"寄件者: {from_addr}\n")
                f.write(f"主旨: {subject}\n")
                f.write(f"日期: {date_header}\n")
                f.write("-" * 40 + "\n")
                f.write(body_text)
            self.logger.debug("[%s] UID=%s 內文已存檔: %s", username, uid_str, text_path)
        except Exception as exc:
            self.logger.error("[%s] UID=%s 內文寫檔失敗: %s", username, uid_str, exc)

        # 附件 (【修改】傳入主旨/寄件者,供帳單推送顯示脈絡)
        self._extract_attachments(msg, day_dir, uid_str, username,
                                  subject=subject, from_addr=from_addr)

        self.logger.info("[%s] UID=%s 下載完成 (主旨: %s)", username, uid_str, subject)

    # ------------------------------------------------------------------
    # 輔助函式
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_email_date(date_header: str) -> datetime:
        """解析郵件 Date 標頭;解析失敗則退回目前系統時間,確保歸檔流程不中斷。"""
        if date_header:
            try:
                parsed = email.utils.parsedate_to_datetime(date_header)
                if parsed is not None:
                    return parsed
            except Exception:
                pass
        return datetime.now()

    @staticmethod
    def _extract_plain_text_body(msg: email.message.Message) -> str:
        """優先取出 text/plain 內文;若僅有 HTML,回傳原始 HTML 內容作為備援。"""
        if msg.is_multipart():
            plain_parts = []
            html_parts = []
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition") or "")
                if "attachment" in content_disposition:
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, errors="ignore")
                except Exception:
                    continue

                if content_type == "text/plain":
                    plain_parts.append(decoded)
                elif content_type == "text/html":
                    html_parts.append(decoded)

            if plain_parts:
                return "\n".join(plain_parts)
            if html_parts:
                return "\n".join(html_parts)
            return ""
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload is None:
                    return msg.get_payload() or ""
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore")
            except Exception:
                return ""

    def _extract_attachments(self, msg: email.message.Message, day_dir: str,
                             uid_str: str, username: str,
                             subject: str = "", from_addr: str = "") -> None:
        if not msg.is_multipart():
            return

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition") or "")
            filename_raw = part.get_filename()

            is_attachment = "attachment" in content_disposition or (
                filename_raw and "inline" not in content_disposition
                and part.get_content_maintype() != "multipart"
            )
            if not filename_raw or not is_attachment:
                continue

            decoded_filename = decode_mime_words(filename_raw)
            name_root, ext = os.path.splitext(decoded_filename)
            safe_name_root = build_safe_basename(name_root) if name_root else "attachment"
            safe_ext = sanitize_filename_chars(ext) if ext else ""

            final_filename = f"{uid_str}_{safe_name_root}{safe_ext}"
            attachment_path = os.path.join(day_dir, final_filename)

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                with open(attachment_path, "wb") as f:
                    f.write(payload)
                self.logger.debug("[%s] UID=%s 附件已存檔: %s", username, uid_str, attachment_path)
            except Exception as exc:
                self.logger.error(
                    "[%s] UID=%s 附件 %s 寫檔失敗: %s",
                    username, uid_str, decoded_filename, exc,
                )
                continue

            # --- PDF 附件:複製/解密到 pdf/ -> 信用卡帳單辨識 ---
            if safe_ext.lower() == ".pdf":
                dest_path, was_enc, decrypted = self._handle_pdf_attachment(
                    attachment_path, username, uid_str)
                # 優先辨識 pdf/ 裡的版本 (已解密,抽文字不需再過密碼);
                # 複製/解密失敗時退回辨識 downloads/ 原檔
                inspect_path = dest_path if dest_path else attachment_path
                self._inspect_pdf_attachment(
                    inspect_path, username, subject, from_addr,
                    original_encrypted=was_enc,
                    is_decrypted_copy=decrypted,
                )

    # ------------------------------------------------------------------
    # 【原有功能】PDF 複製/解密到 pdf/ 資料夾
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_name_collision(dest_dir: str, filename: str) -> str:
        """pdf/ 內若已有同名檔案,自動加上 _1, _2 ... 序號避免覆蓋。"""
        candidate = os.path.join(dest_dir, filename)
        if not os.path.exists(candidate):
            return candidate
        name_root, ext = os.path.splitext(filename)
        index = 1
        while True:
            candidate = os.path.join(dest_dir, f"{name_root}_{index}{ext}")
            if not os.path.exists(candidate):
                return candidate
            index += 1

    def _handle_pdf_attachment(self, attachment_path: str, username: str,
                               uid_str: str) -> tuple:
        """
        偵測 PDF 是否加密:
            - 未加密:直接複製一份到 pdf/ (copy2 保留時間戳,downloads/ 原檔不動)。
            - 已加密:逐一嘗試 ini/passwd.txt 中的密碼,成功後將「解密版」寫入 pdf/。
            - 全部密碼失敗或 pypdf 未安裝:記錄 log,不中斷收信主流程。

        回傳 (pdf/ 中的檔案路徑或 None, 原檔是否加密 Optional[bool], 是否為解密版 bool)
        """
        filename = os.path.basename(attachment_path)

        if not _PYPDF_AVAILABLE:
            self.logger.warning(
                "[%s] UID=%s 偵測到 PDF 附件 %s,但未安裝 pypdf,"
                "無法判斷加密狀態,僅複製原檔至 pdf/。(pip install pypdf)",
                username, uid_str, filename,
            )
            try:
                dest_path = self._resolve_name_collision(PDF_DIR, filename)
                shutil.copy2(attachment_path, dest_path)
                return dest_path, None, False
            except Exception as exc:
                self.logger.error("[%s] UID=%s 複製 PDF %s 失敗: %s",
                                  username, uid_str, filename, exc)
                return None, None, False

        try:
            reader = PdfReader(attachment_path)
        except Exception as exc:
            self.logger.error("[%s] UID=%s 開啟 PDF %s 失敗 (檔案可能損毀): %s",
                              username, uid_str, filename, exc)
            return None, None, False

        # --- 未加密:直接複製 ---
        if not reader.is_encrypted:
            dest_path = self._resolve_name_collision(PDF_DIR, filename)
            try:
                shutil.copy2(attachment_path, dest_path)
                self.logger.info("[%s] UID=%s PDF 未加密,已複製至: %s",
                                 username, uid_str, dest_path)
                return dest_path, False, False
            except Exception as exc:
                self.logger.error("[%s] UID=%s 複製 PDF %s 失敗: %s",
                                  username, uid_str, filename, exc)
                return None, False, False

        # --- 已加密:逐一嘗試密碼 ---
        passwords = self.pdf_passwords
        if not passwords:
            self.logger.error(
                "[%s] UID=%s PDF %s 已加密,但 %s 無可用密碼,跳過。",
                username, uid_str, filename, PASSWD_TXT_PATH,
            )
            return None, True, False

        for password in passwords:
            try:
                # decrypt() 回傳值 > 0 (非 NOT_DECRYPTED) 代表密碼正確
                if reader.decrypt(password):
                    writer = PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    dest_path = self._resolve_name_collision(PDF_DIR, filename)
                    with open(dest_path, "wb") as f:
                        writer.write(f)
                    self.logger.info(
                        "[%s] UID=%s PDF %s 解密成功,已存至: %s",
                        username, uid_str, filename, dest_path,
                    )
                    return dest_path, True, True
            except Exception as exc:
                # 個別密碼嘗試失敗 (含 AES 需 cryptography 套件等情況) 續試下一組
                self.logger.debug(
                    "[%s] UID=%s PDF %s 以某組密碼解密時發生例外: %s",
                    username, uid_str, filename, exc,
                )
                continue

        self.logger.error(
            "[%s] UID=%s PDF %s 已加密,%d 組密碼皆無法解密,跳過。",
            username, uid_str, filename, len(passwords),
        )
        return None, True, False

    # ------------------------------------------------------------------
    # 【新增】PDF 附件辨識:抽文字 -> 判斷 -> 收集待推送
    # ------------------------------------------------------------------
    def _inspect_pdf_attachment(self, pdf_path: str, username: str,
                                subject: str, from_addr: str,
                                original_encrypted: Optional[bool] = None,
                                is_decrypted_copy: bool = False) -> None:
        """
        辨識失敗絕不拋出例外:帳單辨識屬於加值功能,
        任何錯誤只記 log,不能影響收信主流程與 UID 追蹤。
        """
        try:
            text, extract_encrypted = extract_pdf_text(
                pdf_path, self.pdf_passwords, self.logger)

            # 原始加密狀態:優先採用 _handle_pdf_attachment 的判斷結果
            was_encrypted = (original_encrypted
                             if original_encrypted is not None
                             else extract_encrypted)

            if text is None:
                return  # 解密失敗或檔案損毀,extract_pdf_text 已記 log

            if text == "":
                # 沒有文字層 = 掃描圖片型 PDF;目前策略為記 log 觀察,
                # 未來若常出現,再加視覺辨識 (Ollama/VLM) 備援
                self.logger.info("PDF 無文字層 (可能為掃描檔),暫不辨識: %s",
                                 os.path.basename(pdf_path))
                return

            # --- 第一層:信用卡帳單 (訊息格式最豐富) ---
            cc_result = analyze_credit_card_bill(text)
            if cc_result is not None:
                bill = CardBill(
                    pdf_path=pdf_path,
                    account=username,
                    bill_type="信用卡帳單",
                    mail_subject=subject,
                    mail_from=from_addr,
                    bank=cc_result["bank"],
                    amount_due=cc_result["amount_due"],
                    min_payment=cc_result["min_payment"],
                    due_date=cc_result["due_date"],
                    was_encrypted=bool(was_encrypted),
                    is_decrypted_copy=is_decrypted_copy,
                    matched_keywords=cc_result["matched_keywords"],
                )
            else:
                # --- 第二層:通用電子帳單 (電費/水費/電信/瓦斯/稅費...) ---
                eb_result = analyze_electronic_bill(text)
                if eb_result is None:
                    return
                bill = CardBill(
                    pdf_path=pdf_path,
                    account=username,
                    bill_type=eb_result["bill_type"],
                    mail_subject=subject,
                    mail_from=from_addr,
                    bank=eb_result["issuer"],
                    amount_due=eb_result["amount_due"],
                    due_date=eb_result["due_date"],
                    was_encrypted=bool(was_encrypted),
                    is_decrypted_copy=is_decrypted_copy,
                    matched_keywords=eb_result["matched_keywords"],
                )

            # --- 是帳單:另外複製一份到 electronic_bill/,並以該複本推送 ---
            bill.pdf_path = self._archive_electronic_bill(pdf_path)
            self.pending_bills.append(bill)
            self.logger.info(
                "偵測到%s: %s (機構=%s 應繳=%s 截止=%s)",
                bill.bill_type, os.path.basename(pdf_path),
                bill.bank or "?", bill.amount_due or "?", bill.due_date or "?",
            )
        except Exception as exc:
            self.logger.exception("PDF 帳單辨識流程例外 (%s): %s",
                                  os.path.basename(pdf_path), exc)

    def _archive_electronic_bill(self, pdf_path: str) -> str:
        """
        將判定為帳單的 PDF 另外複製一份到 electronic_bill/。
        回傳 electronic_bill/ 中的複本路徑 (供 Telegram 推送);
        複製失敗時回傳原路徑,確保推送不受影響。
        """
        try:
            dest_path = self._resolve_name_collision(
                ELECTRONIC_BILL_DIR, os.path.basename(pdf_path))
            shutil.copy2(pdf_path, dest_path)
            self.logger.info("帳單已歸檔至: %s", dest_path)
            return dest_path
        except Exception as exc:
            self.logger.error("複製帳單到 electronic_bill/ 失敗 (%s): %s",
                              os.path.basename(pdf_path), exc)
            return pdf_path


# ---------------------------------------------------------------------------
# 進入點
# ---------------------------------------------------------------------------

def main() -> None:
    logger = setup_logging()
    logger.info("===== mail_sync_script 開始執行 (BASE_DIR=%s) =====", BASE_DIR)

    try:
        downloader = EmailDownloader(logger)
        downloader.run()
    except FileNotFoundError:
        # 設定檔不存在時,_load_config 已記錄詳細訊息並建立範本,此處僅正常結束
        pass
    except Exception as exc:
        logger.exception("主流程發生未預期錯誤: %s", exc)
    finally:
        logger.info("===== mail_sync_script 執行結束 =====")


if __name__ == "__main__":
    main()