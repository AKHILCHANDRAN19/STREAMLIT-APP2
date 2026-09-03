import re
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
        response = requests.get(GOLD_URL_GOODRETURNS, impersonate="chrome110", timeout=15)
        if response.status_code != 200:
            return {"error": f"Failed with HTTP {response.status_code}"}

        soup = BeautifulSoup(response.text, "html.parser")

        # --- Today's & Yesterday's 22K Rates ---
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

        # --- History Table (Last 10 Days to allow math for the past 7 days) ---
        history = []
        for table in soup.find_all("table", class_="table-conatiner"):
            headers = [th.text.strip().lower() for th in table.find_all("th")]
            if "date" in headers:
                for row in table.find("tbody").find_all("tr")[:10]:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        date_str = cols[0].text.strip().split(",")[0]
                        price_22k = clean_price(cols[2].text)
                        history.append({
                            "date": date_str,
                            "1g": price_22k,
                            "8g": price_22k * 8
                        })
                if history:
                    break

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
# 🌟 2. AKGSMA SCRAPER (TODAY'S 22K RATE)
# ==========================================
def scrape_akgsma_22k():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
        response = requests.get(AKGSMA_URL, headers=headers, impersonate="chrome120", timeout=15)

        if response.status_code == 200 and "Just a moment..." not in response.text:
            soup = BeautifulSoup(response.text, "html.parser")
            p_22k_1g = 0

            for li in soup.find_all("li"):
                text = li.text.strip().upper()
                if "22K" in text and "₹" in text:
                    p_22k_1g = int(re.sub(r"[^\d]", "", text.split("₹")[-1]))
                    break

            if p_22k_1g == 0:
                rate_list = soup.find("ul", class_=re.compile("list-block"))
                if rate_list:
                    match = re.search(r"22K916.*?₹\s*(\d+)", rate_list.get_text(separator=" | "))
                    if match:
                        p_22k_1g = int(match.group(1))

            if p_22k_1g > 0:
                return {
                    "today_1g": float(p_22k_1g),
                    "today_8g": float(p_22k_1g * 8)
                }
            else:
                return {"error": "Could not locate 22K rate in page structure."}
        else:
            return {"error": f"Failed with status code: {response.status_code}"}

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
        lines.append(f"❌ **Error fetching AKGSMA:** {akg_data['error']}")
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
        lines.append(f"❌ **Error fetching GoodReturns:** {gr_data['error']}")
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


# ==========================================
# 🚀 CLI MAIN EXECUTION
# ==========================================
def main():
    print(get_goodreturns_report())

if __name__ == "__main__":
    main()

