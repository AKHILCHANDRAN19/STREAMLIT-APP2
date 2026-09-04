import re
import time
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

# ==========================================
# ⚙️ CONFIGURATION & TIMEZONE (IST)
# ==========================================
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

GOLD_URL_GOODRETURNS = "https://www.goodreturns.in/gold-rates/kerala.html"
AKGSMA_URL = "https://akgsma-com.translate.goog/?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp"


def clean_price(price_str: str) -> float:
    """Cleans currency strings into a float."""
    if not price_str or price_str.strip() == "-":
        return 0.0
    price_str = price_str.split("(")[0]
    cleaned = re.sub(r"[^\d.]", "", price_str)
    return float(cleaned) if cleaned else 0.0


def format_inr(amount: float) -> str:
    """Formats a number into Indian Rupee format (e.g. ₹56,200)."""
    try:
        s = str(int(amount))
        if len(s) <= 3:
            return f"₹{s}"
        last_three, remaining = s[-3:], s[:-3]
        formatted = ",".join([remaining[max(i - 2, 0):i] for i in range(len(remaining), 0, -2)][::-1])
        return f"₹{formatted},{last_three}"
    except Exception:
        return f"₹{amount:,.0f}"


# ==========================================
# 🟡 1. GOODRETURNS SCRAPER (22K RATE)
# ==========================================
def scrape_goodreturns_22k():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
        url = f"{GOLD_URL_GOODRETURNS}?_ts={int(time.time())}"

        response = requests.get(url, headers=headers, impersonate="chrome120", timeout=20)
        if response.status_code != 200 or len(response.text) < 1000:
            return {"error": f"Failed with HTTP {response.status_code}"}

        soup = BeautifulSoup(response.text, "html.parser")

        today_22k_1g = 0.0
        yest_22k_1g = 0.0

        header = soup.find(lambda tag: tag.name in ["h2", "h3"] and re.search(r"Today 22 Carat", tag.text, re.IGNORECASE))
        if header and header.find_next("table"):
            for row in header.find_next("table").find("tbody").find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 3 and cols[0].text.strip() == "1":
                    today_22k_1g = clean_price(cols[1].text)
                    yest_22k_1g = clean_price(cols[2].text)
                    break

        if today_22k_1g == 0.0:
            gold_header = soup.find(lambda tag: tag.name in ["h2", "h3"] and re.search(r"Today Gold Price", tag.text, re.IGNORECASE))
            if gold_header and gold_header.find_next("table"):
                for row in gold_header.find_next("table").find("tbody").find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) >= 4 and cols[0].text.strip() == "1":
                        td_txt = cols[2].text
                        today_22k_1g = clean_price(td_txt)
                        change = 0.0
                        if "(" in td_txt and ")" in td_txt:
                            change_str = re.sub(r"[^\d.-]", "", td_txt.split("(")[1].split(")")[0])
                            if change_str and change_str != "-":
                                change = float(change_str)
                        yest_22k_1g = today_22k_1g - change
                        break

        history = []
        for table in soup.find_all("table", class_="table-conatiner"):
            headers_list = [th.text.strip().lower() for th in table.find_all("th")]
            if "date" in headers_list:
                for row in table.find("tbody").find_all("tr")[:10]:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        date_str = cols[0].text.strip().split(",")[0]
                        price_22k = clean_price(cols[2].text)
                        if price_22k > 0:
                            history.append({
                                "date": date_str,
                                "1g": price_22k,
                                "8g": price_22k * 8
                            })
                if history:
                    break

        if today_22k_1g == 0.0:
            return {"error": "Could not parse GoodReturns 22K rate."}

        return {
            "today_1g": today_22k_1g,
            "today_8g": today_22k_1g * 8,
            "yest_1g": yest_22k_1g,
            "yest_8g": yest_22k_1g * 8,
            "diff_1g": today_22k_1g - yest_22k_1g,
            "diff_8g": (today_22k_1g - yest_22k_1g) * 8,
            "history": history
        }

    except Exception as e:
        return {"error": str(e)}


# ==========================================
# 🌟 2. AKGSMA SCRAPER (VIA GOOGLE TRANSLATE PROXY)
# ==========================================
def scrape_akgsma_22k():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Referer": "https://translate.google.com/"
        }

        # Follow redirects through the translate.goog proxy
        response = requests.get(
            AKGSMA_URL,
            headers=headers,
            impersonate="chrome120",
            allow_redirects=True,
            timeout=20
        )

        if response.status_code != 200:
            return {"error": f"Translate Proxy returned status {response.status_code}"}

        html_content = response.text
        if "Just a moment..." in html_content or len(html_content) < 500:
            return {"error": "Blocked by security challenge."}

        soup = BeautifulSoup(html_content, "html.parser")
        p_22k_1g = 0

        # Strategy 1: Targeted regex on full rendered text
        # Handles '22K916 (1gm) - ₹ 14240', '22K 916 (1gm) - Rs. 14240', '22K - ₹ 14,240'
        full_text = soup.get_text(separator=" ")
        patterns = [
            r"22K(?:916)?\s*(?:\([^)]*\))?\s*[-:]?\s*(?:₹|Rs\.?|INR)?\s*([0-9,]{4,7})",
            r"22\s*Carat.*?₹\s*([0-9,]{4,7})",
            r"22K.*?₹\s*([0-9,]{4,7})"
        ]

        for pat in patterns:
            match = re.search(pat, full_text, re.IGNORECASE)
            if match:
                val = int(re.sub(r"[^\d]", "", match.group(1)))
                if 5000 < val < 50000:  # Valid price sanity check
                    p_22k_1g = val
                    break

        # Strategy 2: Search within list elements and divs directly
        if p_22k_1g == 0:
            for el in soup.find_all(["li", "p", "div", "span"]):
                txt = el.text.strip().upper()
                if "22K" in txt and any(sym in txt for sym in ["₹", "RS", "INR"]):
                    sub_m = re.search(r"(?:₹|RS\.?|INR)?\s*([0-9,]{4,7})", txt)
                    if sub_m:
                        val = int(re.sub(r"[^\d]", "", sub_m.group(1)))
                        if 5000 < val < 50000:
                            p_22k_1g = val
                            break

        if p_22k_1g > 0:
            return {
                "today_1g": float(p_22k_1g),
                "today_8g": float(p_22k_1g * 8)
            }
        else:
            return {"error": "Rate pattern not found in translated page structure."}

    except Exception as e:
        return {"error": str(e)}


# ==========================================
# 💬 BOT TELEGRAM CARD FORMATTERS
# ==========================================
def get_akgsma_report() -> str:
    now_ist = datetime.now(IST_TIMEZONE)
    today_date_str = now_ist.strftime("%d %B %Y (%A)")
    today_time_str = now_ist.strftime("%I:%M %p IST")

    akg_data = scrape_akgsma_22k()

    lines = [
        f"📅 **TODAY'S DATE :** `{today_date_str}`",
        f"🕒 **CURRENT TIME :** `{today_time_str}`",
        "──────────────────────────────",
        "🏛️ **AKGSMA (KERALA) - TODAY'S 22K GOLD RATE**",
        "──────────────────────────────"
    ]

    if "error" in akg_data:
        lines.append(f"❌ **Error fetching AKGSMA:** `{akg_data['error']}`")
    else:
        lines.append(f"🔸 **1 Gram (22K / 916) :** `{format_inr(akg_data['today_1g'])}`")
        lines.append(f"🔸 **1 Pavan (8 Grams)   :** `{format_inr(akg_data['today_8g'])}`")

    return "\n".join(lines)


def get_goodreturns_report() -> str:
    now_ist = datetime.now(IST_TIMEZONE)
    today_date_str = now_ist.strftime("%d %B %Y (%A)")
    today_time_str = now_ist.strftime("%I:%M %p IST")

    gr_data = scrape_goodreturns_22k()

    lines = [
        f"📅 **TODAY'S DATE :** `{today_date_str}`",
        f"🕒 **CURRENT TIME :** `{today_time_str}`",
        "──────────────────────────────",
        "🌐 **GOODRETURNS - TODAY'S 22K GOLD RATE & DIFF**",
        "──────────────────────────────"
    ]

    if "error" in gr_data:
        lines.append(f"❌ **Error fetching GoodReturns:** `{gr_data['error']}`")
        return "\n".join(lines)

    diff_1g = gr_data['diff_1g']
    diff_8g = gr_data['diff_8g']

    if diff_1g > 0:
        trend_str = f"🔺 UP by {format_inr(abs(diff_1g))} per gram ({format_inr(abs(diff_8g))} per pavan)"
    elif diff_1g < 0:
        trend_str = f"🔻 DOWN by {format_inr(abs(diff_1g))} per gram ({format_inr(abs(diff_8g))} per pavan)"
    else:
        trend_str = "▬ NO CHANGE (Flat compared to yesterday)"

    lines.append(f"🔸 **Today 1 Gram (22K) :** `{format_inr(gr_data['today_1g'])}`")
    lines.append(f"🔸 **Today 1 Pavan (8g)  :** `{format_inr(gr_data['today_8g'])}`")
    lines.append(f"🔸 **Yesterday 1 Gram    :** `{format_inr(gr_data['yest_1g'])}`")
    lines.append(f"🔸 **Yesterday 1 Pavan   :** `{format_inr(gr_data['yest_8g'])}`")
    lines.append(f"📊 **Yesterday Difference:** {trend_str}")
    lines.append("\n──────────────────────────────")
    lines.append("📈 **GOODRETURNS - 22K PRICE HISTORY (LAST 10 DAYS)**")
    lines.append("──────────────────────────────")
    lines.append("```text")
    lines.append(f"{'#':<3} | {'DATE':<14} | {'1 GRAM RATE':<14} | {'1 PAVAN (8g)'}")
    lines.append("──────────────────────────────────────────────────")

    history_items = gr_data.get("history", [])
    if history_items:
        for idx, item in enumerate(history_items, 1):
            label = f"{item['date']} (Today)" if idx == 1 else item['date']
            lines.append(f"{idx:<3} | {label:<14} | {format_inr(item['1g']):<14} | {format_inr(item['8g'])}")
    else:
        for i in range(10):
            day_dt = now_ist - timedelta(days=i)
            d_str = day_dt.strftime("%b %d")
            rate = gr_data['today_1g'] if i == 0 else gr_data['yest_1g']
            lines.append(f"{i+1:<3} | {d_str:<14} | {format_inr(rate):<14} | {format_inr(rate * 8)}")

    lines.append("```")
    return "\n".join(lines)


def main():
    print(get_goodreturns_report())
    print()
    print(get_akgsma_report())


if __name__ == "__main__":
    main()
