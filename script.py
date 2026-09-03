import datetime
import re
import scrapping
from indic_numtowords import num2words

# ==========================================
# ⚙️ HELPER FUNCTIONS
# ==========================================
def to_ml_words(num):
    """Converts integers to Malayalam words for precise TTS pronunciation."""
    try:
        return num2words(int(num), lang='ml')
    except Exception:
        return str(num)

ENG_TO_ML_MONTHS = {
    "Jan": "ജനുവരി", "Feb": "ഫെബ്രുവരി", "Mar": "മാർച്ച്", "Apr": "ഏപ്രിൽ",
    "May": "മെയ്", "Jun": "ജൂൺ", "Jul": "ജൂലൈ", "Aug": "ഓഗസ്റ്റ്",
    "Sep": "സെപ്റ്റംബർ", "Oct": "ഒക്ടോബർ", "Nov": "നവംബർ", "Dec": "ഡിസംബർ"
}

def translate_date(date_str):
    """Converts English date strings (e.g., 'Sep 03') to Malayalam (e.g., 'സെപ്റ്റംബർ മൂന്ന്')."""
    for eng, ml in ENG_TO_ML_MONTHS.items():
        if eng in date_str:
            day_match = re.search(r'\d+', date_str)
            if day_match:
                day_words = to_ml_words(int(day_match.group()))
                return f"{ml} {day_words}"
            return date_str.replace(eng, ml)
    return date_str


# ==========================================
# 📝 MAIN SCRIPT GENERATOR
# ==========================================
def generate_audio_script(source="akgsma"):
    """
    Generates the full Malayalam script.
    source: 'akgsma' for /scriptakg or 'goodreturns' for /scriptgd
    """
    # 1. Fetch Data
    gr_data = scrapping.scrape_goodreturns_22k()
    
    if source == "akgsma":
        akg_data = scrapping.scrape_akgsma_22k()
        today_1g = akg_data.get('today_1g', gr_data.get('today_1g', 0))
    else:
        today_1g = gr_data.get('today_1g', 0)
        
    yesterday_1g = gr_data.get('yest_1g', 0)
    
    # Extract chronological 7-day history from GoodReturns
    history_items = gr_data.get("history", [])
    if not history_items:
        return "❌ Error: Could not retrieve market history."
        
    # Reverse to get oldest to newest (last 7 days)
    chronological_history = list(reversed(history_items[:7]))
    dates = [translate_date(item['date'].replace(" (Today)", "")) for item in chronological_history]
    weekly_prices = [item['1g'] for item in chronological_history]
    
    # Ensure the latest array value exactly matches our chosen today's price
    if weekly_prices:
        weekly_prices[-1] = today_1g

    # 2. Daily Price Calculations (Pavan)
    pavan_price_today = today_1g * 8
    pavan_price_yesterday = yesterday_1g * 8
    pavan_change_amount = pavan_price_today - pavan_price_yesterday

    # 3. Weekly Trend Calculations
    start_price = weekly_prices[0]
    end_price = weekly_prices[-1]
    weekly_price_difference = abs(start_price - end_price)
    
    week_high_price = max(weekly_prices)
    week_high_date = dates[weekly_prices.index(week_high_price)]
    
    week_low_price = min(weekly_prices)
    week_low_date = dates[weekly_prices.index(week_low_price)]

    # Weekly Phrase Logic
    if sorted(weekly_prices) == weekly_prices:
        weekly_trend_phrase = "തുടർച്ചയായ കുതിപ്പാണ് രേഖപ്പെടുത്തിയിരിക്കുന്നത്"
    elif sorted(weekly_prices, reverse=True) == weekly_prices:
        weekly_trend_phrase = "തുടർച്ചയായ ഇടിവാണ് രേഖപ്പെടുത്തിയിരിക്കുന്നത്"
    else:
        weekly_trend_phrase = "വില കൂടിയും കുറഞ്ഞുമുള്ള പ്രവണതയാണ് കാണിക്കുന്നത്"

    # Summary Trend Word Logic
    if end_price < start_price:
        summary_trend_word = "വൻ ഇടിവാണ്"
    elif end_price > start_price:
        summary_trend_word = "വർദ്ധനവാണ്"
    else:
        summary_trend_word = "മാറ്റമില്ലാത്ത അവസ്ഥയാണ്"

    # Time of Day Logic
    hour = datetime.datetime.now().hour
    if hour < 12:
        time_of_day = "രാവിലെ"
    elif hour < 16:
        time_of_day = "ഉച്ചയ്ക്ക്"
    else:
        time_of_day = "വൈകുന്നേരം"

    # 4. Construct Part 1: Seven-Day Comparison
    # Replaced '22' with 'ഇരുപത്തി രണ്ട്'
    part1_template = "നമസ്കാരം. ഇന്നത്തെ സ്വർണ്ണവില വിവരങ്ങളിലേക്ക് സ്വാഗതം. ഇന്നലെ സ്വർണ്ണ വിപണി അവസാനമായി ട്രേഡ് ചെയ്തത് ഗ്രാമിന് {yesterday_price} രൂപ എന്ന നിരക്കിലാണ്. കഴിഞ്ഞ ഒരാഴ്ചത്തെ കണക്കുകൾ പരിശോധിക്കുമ്പോൾ വിപണിയിൽ {weekly_trend_phrase}. ഈ ആഴ്ചയിലെ വിപണി വിലയിരുത്തുമ്പോൾ, സ്വർണ്ണം ഏറ്റവും ഉയരത്തിൽ എത്തിയത് {week_high_date}-ൽ ഗ്രാമിന് {week_high_price} രൂപ എന്ന നിരക്കിലാണ്. എന്നാൽ വിപണി ഏറ്റവും താഴെത്തട്ടിൽ എത്തിയത് {week_low_date}-ൽ ഗ്രാമിന് {week_low_price} രൂപയിലുമാണ്. ചുരുക്കത്തിൽ, കഴിഞ്ഞ ഒരാഴ്ചക്കിടെ ഒരു ഗ്രാം ഇരുപത്തി രണ്ട് കാരറ്റ് സ്വർണ്ണത്തിന് {price_difference} രൂപയുടെ {summary_trend_word} കേരള വിപണിയിൽ ഉണ്ടായിട്ടുള്ളത്."
    
    part1_script = part1_template.format(
        yesterday_price=to_ml_words(yesterday_1g),
        weekly_trend_phrase=weekly_trend_phrase,
        week_high_date=week_high_date,
        week_high_price=to_ml_words(week_high_price),
        week_low_date=week_low_date,
        week_low_price=to_ml_words(week_low_price),
        price_difference=to_ml_words(weekly_price_difference),
        summary_trend_word=summary_trend_word
    )

    # 5. Construct Part 2: Today's Status
    # Replaced '22' with 'ഇരുപത്തി രണ്ട്' and reordered to state 1 gram first, then 1 pavan
    if pavan_change_amount > 0:
        change_status = "വർദ്ധിച്ചു"
        part2_template = "ഇന്ന് {time_of_day} കേരളത്തിൽ സ്വർണ്ണവില ഒരു പവന് {pavan_change_amount} രൂപ {change_status}. ഇതോടെ നയൻ വൺ സിക്സ് ബി.ഐ.എസ് ഹോൾമാർക്ക് ചെയ്ത ഇരുപത്തി രണ്ട് കാരറ്റ് സ്വർണ്ണം ഒരു ഗ്രാമിന് {gram_price} രൂപയും, ഒരു പവന് {pavan_price} രൂപയുമാണ് ഇന്നത്തെ നിരക്ക്."
    elif pavan_change_amount < 0:
        change_status = "കുറഞ്ഞു"
        part2_template = "ഇന്ന് {time_of_day} കേരളത്തിൽ സ്വർണ്ണവില ഒരു പവന് {pavan_change_amount} രൂപ {change_status}. ഇതോടെ നയൻ വൺ സിക്സ് ബി.ഐ.എസ് ഹോൾമാർക്ക് ചെയ്ത ഇരുപത്തി രണ്ട് കാരറ്റ് സ്വർണ്ണം ഒരു ഗ്രാമിന് {gram_price} രൂപയും, ഒരു പവന് {pavan_price} രൂപയുമാണ് ഇന്നത്തെ നിരക്ക്."
    else:
        change_status = ""
        part2_template = "ഇന്ന് {time_of_day} കേരളത്തിൽ സ്വർണ്ണവിലയിൽ മാറ്റമില്ല. നയൻ വൺ സിക്സ് ബി.ഐ.എസ് ഹോൾമാർക്ക് ചെയ്ത ഇരുപത്തി രണ്ട് കാരറ്റ് സ്വർണ്ണം ഒരു ഗ്രാമിന് {gram_price} രൂപയും, ഒരു പവന് {pavan_price} രൂപയുമാണ് ഇന്നത്തെ നിരക്ക്."

    part2_script = part2_template.format(
        time_of_day=time_of_day,
        pavan_change_amount=to_ml_words(abs(pavan_change_amount)),
        change_status=change_status,
        pavan_price=to_ml_words(pavan_price_today),
        gram_price=to_ml_words(today_1g)
    )

    # Combine into two distinct sections
    return f"**വിപണി വിശകലനം (Comparison)**\n{part1_script}\n\n**ഇന്നത്തെ വില (Today Price)**\n{part2_script}"


# ==========================================
# ⚙️ COMMAND HANDLERS
# ==========================================
def get_script_akg():
    """Triggered by /scriptakg"""
    return generate_audio_script(source="akgsma")

def get_script_gd():
    """Triggered by /scriptgd"""
    return generate_audio_script(source="goodreturns")

if __name__ == "__main__":
    # Test Output
    print("\n--- /scriptakg Output ---")
    print(get_script_akg())
