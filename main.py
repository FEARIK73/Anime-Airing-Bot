import os
import requests
import asyncio
import html
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from flask import Flask
from threading import Thread
import nest_asyncio

nest_asyncio.apply()

# ================= ENV =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

API_URL = "https://graphql.anilist.co"
CHANNEL_IDS = [-1002423492460, -1002318432801]

PRE_ALERT_IDS = set()
POST_ALERT_IDS = set()
UTC = timezone.utc

# ================= FLASK (KEEP ALIVE) =================
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    # Use threaded=True to allow concurrent requests
    web_app.run(host="0.0.0.0", port=8080, threaded=True)

# -------- AUTO DELETE -------- #
async def auto_delete(client, chat_id, message_id, delay=300):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
    except:
        pass

# -------- SAFE REQUEST -------- #
def safe_request(query, variables=None):
    try:
        res = requests.post(
            API_URL,
            json={'query': query, 'variables': variables},
            timeout=10
        )
        data = res.json()
        if "data" not in data or data["data"] is None:
            return None
        return data["data"]
    except Exception as e:
        print("Request Error:", e)
        return None

# -------- FETCH SCHEDULE -------- #
def fetch_schedule(day_offset=0):
    now_utc = datetime.now(UTC)
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    target_date = (now_ist + timedelta(days=day_offset)).date()

    start_ts = int((now_utc - timedelta(hours=12)).timestamp())
    end_ts = int((now_utc + timedelta(days=3)).timestamp())

    query = """
    query ($start: Int, $end: Int) {
      Page(page: 1, perPage: 50) {
        airingSchedules(airingAt_greater: $start, airingAt_lesser: $end) {
          episode
          airingAt
          media { title { english romaji } }
        }
      }
    }
    """

    res = safe_request(query, {"start": start_ts, "end": end_ts})
    if not res:
        return "API Error"

    data = res["Page"]["airingSchedules"]
    result = []

    for anime in data:
        utc_time = datetime.fromtimestamp(anime["airingAt"], UTC)
        ist_time = utc_time + timedelta(hours=5, minutes=30)

        if ist_time.date() != target_date:
            continue

        title_raw = anime["media"]["title"]["english"] or anime["media"]["title"]["romaji"]
        title = html.escape(title_raw)
        ep = anime["episode"]

        delta = ist_time - now_ist
        if delta.total_seconds() < 0:
            status = "Aired"
        else:
            total_minutes = int(delta.total_seconds() // 60)
            hours, minutes = divmod(total_minutes, 60)
            days, hours = divmod(hours, 24)
            if days > 0:
                status = f"In {days}d {hours}h {minutes}m"
            else:
                status = f"In {hours}h {minutes}m"

        text = f"""<b>✶ {title}</b>
<code>│ Ep     :</code> {ep}
<code>│ Time   :</code> {ist_time.strftime('%I:%M %p')}
<code>│ Status :</code> {status}
<code>└───────────────────</code>"""
        result.append((ist_time, text))

    result.sort()
    final_text = "\n".join([x[1] for x in result])
    return final_text if final_text else "No airing found 🙃"

# -------- ALERT SYSTEM -------- #
async def auto_airing_alert(app):
    while True:
        try:
            now_ts = int(datetime.now(UTC).timestamp())
            end = now_ts + 3600

            query = """
            query ($start: Int, $end: Int) {
              Page(perPage: 50) {
                airingSchedules(airingAt_greater: $start, airingAt_lesser: $end) {
                  episode
                  airingAt
                  media { title { english romaji } }
                }
              }
            }
            """

            res = safe_request(query, {"start": now_ts, "end": end})
            if not res:
                await asyncio.sleep(60)
                continue

            for anime in res["Page"]["airingSchedules"]:
                unique_id = f"{anime['media']['title']['romaji']}_{anime['episode']}"
                air_ts = anime["airingAt"]

                title_raw = anime["media"]["title"]["english"] or anime["media"]["title"]["romaji"]
                title = html.escape(title_raw)
                ep = anime["episode"]

                # PRE ALERT
                if unique_id not in PRE_ALERT_IDS and 0 < air_ts - now_ts <= 600:
                    PRE_ALERT_IDS.add(unique_id)
                    m, s = divmod(air_ts - now_ts, 60)
                    text = f"""╰► Upcoming Episode Alert

<b>✶ {title}</b>
<code>│ Ep     :</code> {ep}
<code>│ Airs in:</code> {m} min {s} sec
<code>└────────────────────</code>"""
                    for ch in CHANNEL_IDS:
                        await app.send_message(ch, text, parse_mode=ParseMode.HTML)

                # POST ALERT
                if unique_id not in POST_ALERT_IDS and -30 <= air_ts - now_ts <= 30:
                    POST_ALERT_IDS.add(unique_id)
                    text = f"""╰► NEW EPISODE RELEASED

<b>✶ {title}</b>
<code>│ Ep     :</code> {ep}
<code>│ Status :</code> Just Aired!
<code>└────────────────────</code>"""
                    for ch in CHANNEL_IDS:
                        await app.send_message(ch, text, parse_mode=ParseMode.HTML)

        except Exception as e:
            print("Alert Error:", e)

        await asyncio.sleep(30)

# -------- BOT -------- #
app = Client("airing_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("today"))
async def today(client, m):
    msg = await m.reply("Today's Schedule:\n\n" + fetch_schedule(0), parse_mode=ParseMode.HTML)
    asyncio.create_task(auto_delete(client, msg.chat.id, msg.id))

@app.on_message(filters.command("tomorrow"))
async def tomorrow(client, m):
    msg = await m.reply("Tomorrow's Schedule:\n\n" + fetch_schedule(1), parse_mode=ParseMode.HTML)
    asyncio.create_task(auto_delete(client, msg.chat.id, msg.id))

# -------- MAIN -------- #
async def start_bot():
    await app.start()
    asyncio.create_task(auto_airing_alert(app))
    print("Bot started and running...")
    await idle()

if __name__ == "__main__":
    # Start Flask keep-alive in a separate thread
    Thread(target=run_web).start()
    
    # Start bot in asyncio
    asyncio.run(start_bot())
