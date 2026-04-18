import nest_asyncio
nest_asyncio.apply()

import requests
import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN

# -------- CONFIG --------
API_URL = "https://graphql.anilist.co"
BASE_LINK = "http://t.me/Markscans_bot?start=single_-1002097289861_{}"
CHANNEL_IDS = [-1002423492460]
PRE_ALERT_IDS = set()
POST_ALERT_IDS = set()
MAX_ALERT_IDS = 500
UTC = timezone.utc

app = Client("Chomu_Bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------- AUTO DELETE --------
async def auto_delete(client, chat_id, message_id, delay=300):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
    except:
        pass

# -------- BUTTONS --------
def get_buttons(day="today"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(" Today", callback_data="today"),
            InlineKeyboardButton(" Tomorrow", callback_data="tomorrow")
        ]
    ])

# -------- SAFE REQUEST --------
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

# -------- FETCH SCHEDULE --------
def fetch_schedule(day_offset=0):
    now_utc = datetime.now(UTC)
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    target_date = (now_ist + timedelta(days=day_offset)).date()
    start_ist = datetime.combine(target_date, datetime.min.time())
    end_ist = datetime.combine(target_date, datetime.max.time())
    start_utc = start_ist - timedelta(hours=5, minutes=30)
    end_utc = end_ist - timedelta(hours=5, minutes=30)
    start_ts = int(start_utc.replace(tzinfo=UTC).timestamp())
    end_ts = int(end_utc.replace(tzinfo=UTC).timestamp())

    query = """
    query ($start: Int, $end: Int) {
      Page(page: 1, perPage: 50) {
        airingSchedules(airingAt_greater: $start, airingAt_lesser: $end) {
          episode
          airingAt
          media { 
            title { english romaji }
            countryOfOrigin
          }
        }
      }
    }
    """
    res = safe_request(query, {"start": start_ts, "end": end_ts})
    if not res or "Page" not in res:
        return "API Error | Anilist issue"

    data = res["Page"].get("airingSchedules", [])
    if not data:
        return "No airing found 🙃"

    result = []
    for anime in data:
        utc_time = datetime.fromtimestamp(anime["airingAt"], UTC)
        ist_time = utc_time + timedelta(hours=5, minutes=30)
        title_raw = anime["media"]["title"]["english"] or anime["media"]["title"]["romaji"]
        title = html.escape(title_raw)
        ep = anime["episode"]

        delta = ist_time - now_ist
        if delta.total_seconds() < 0:
            status = "Aired  ✅"
        else:
            total_minutes = int(delta.total_seconds() // 60)
            hours, minutes = divmod(total_minutes, 60)
            days, hours = divmod(hours, 24)
            status = f"In {days}d {hours}h {minutes}m" if days > 0 else f"In {hours}h {minutes}m"

        text = f"""<b>✶ {title}</b>
│ Ep      : {ep}
│ Time   : {ist_time.strftime('%I:%M %p')}
│ Status : {status}
└────────────────"""
        result.append((ist_time, text))

    result.sort()
    return "\n".join([x[1] for x in result])

# -------- CAPTION GENERATOR --------
def fetch_anime_caption(query_text):
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title { english romaji }
        description
        genres
        averageScore
      }
    }
    """
    res = safe_request(query, {"search": query_text})
    if not res or "Media" not in res:
        return "Anime name not found 🙃 — correct name plz 🙏"

    m = res["Media"]

    title = m["title"]["english"] or m["title"]["romaji"]

    raw_desc = m.get("description") or "N/A"
    clean_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()
    synopsis = clean_desc[:45] + "..." if len(clean_desc) > 45 else clean_desc

    genres = ", ".join(m.get("genres", [])) or "N/A"
    rating = m.get("averageScore") or "N/A"

    caption = (
        f"<b>{html.escape(title)}</b>\n\n"
        f"• Synopsis : {html.escape(synopsis)}\n"
        f"• Genres - <i>{html.escape(genres)}</i>\n"
        f"• Rating - <i>{rating}</i>"
    )
    return caption

# -------- DONGHUA CAPTION GENERATOR (Jikan/MAL) --------
def fetch_donghua_caption(query_text):
    try:
        res = requests.get(
            "https://api.jikan.moe/v4/anime",
            params={"q": query_text, "limit": 1},
            timeout=10
        )
        data = res.json()
        if not data.get("data"):
            return "Donghua name not found 🙃 — correct name plz 🙏"

        m = data["data"][0]

        title = m.get("title_english") or m.get("title") or "Unknown"

        raw_status = m.get("status") or "Unknown"
        status_map = {
            "Finished Airing": "Completed",
            "Currently Airing": "Ongoing",
            "Not yet aired": "Upcoming"
        }
        status = status_map.get(raw_status, raw_status)

        seasons = m.get("season") or ""
        year = m.get("year") or ""
        if seasons and year:
            season_val = f"{seasons.capitalize()} {year}"
        elif year:
            season_val = str(year)
        else:
            season_val = "01"

        episodes = m.get("episodes") or ""

        caption = (
            f"✦ <b>{html.escape(title)}</b>\n"
            f"<b>╭━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>‣ Status :</b> {status}\n"
            f"<b>‣ Seasons :</b> {season_val}\n"
            f"<b>‣ Episodes :</b> {episodes}\n"
            f"<b>‣ Audio :</b> Chinese [Eng-Sub]\n"
            f"<b>‣ Quality :</b> 480p | 720p | 1080p | 4k\n"
            f"<b>╰━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✦ Powered By :</b> @Donghua_Heavens"
        )
        return caption

    except Exception as e:
        print("Donghua fetch error:", e)
        return "Error fetching donghua info 🙃 — try again"


# -------- ALERT SYSTEM --------
async def auto_airing_alert():
    while True:
        try:
            now_ts = int(datetime.now(UTC).timestamp())
            end_ts = now_ts + 3600

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

            res = safe_request(query, {"start": now_ts - 60, "end": end_ts})
            if not res:
                await asyncio.sleep(60)
                continue

            for anime in res["Page"].get("airingSchedules", []):
                unique_id = f"{anime['media']['title']['romaji']}_{anime['episode']}"
                air_ts = anime["airingAt"]
                title_raw = anime["media"]["title"]["english"] or anime["media"]["title"]["romaji"]
                title = html.escape(title_raw)
                ep = anime["episode"]

                if unique_id not in PRE_ALERT_IDS and 0 < air_ts - now_ts <= 600:
                    PRE_ALERT_IDS.add(unique_id)
                    if len(PRE_ALERT_IDS) > MAX_ALERT_IDS:
                        oldest = next(iter(PRE_ALERT_IDS))
                        PRE_ALERT_IDS.discard(oldest)

                    msgs = []
                    for channel in CHANNEL_IDS:
                        m = await app.send_message(
                            channel,
                            f"╰► Upcoming Episode Alert\n\n<b>✶ {title}</b>\n│ Ep        : {ep}\n│ Airs in : calculating...\n└───────────────",
                            parse_mode=ParseMode.HTML
                        )
                        msgs.append(m)

                    while True:
                        await asyncio.sleep(5)
                        now_ts2 = int(datetime.now(UTC).timestamp())
                        remaining = air_ts - now_ts2
                        if remaining <= 0:
                            post_text = f"╰► NEW EPISODE RELEASED\n\n<b>✶ {title}</b>\n│ Ep        : {ep}\n│ Status : Just Aired! ✅\n└───────────────"
                            for msg in msgs:
                                try:
                                    await msg.edit_text(post_text, parse_mode=ParseMode.HTML)
                                except:
                                    pass
                            POST_ALERT_IDS.add(unique_id)
                            if len(POST_ALERT_IDS) > MAX_ALERT_IDS:
                                oldest = next(iter(POST_ALERT_IDS))
                                POST_ALERT_IDS.discard(oldest)
                            break
                        else:
                            m2, s2 = divmod(remaining, 60)
                            countdown_text = f"╰► Upcoming Episode Alert\n\n<b>✶ {title}</b>\n│ Ep     : {ep}\n│ Airs in: {m2} min {s2} sec\n└───────────────"
                            for msg in msgs:
                                try:
                                    await msg.edit_text(countdown_text, parse_mode=ParseMode.HTML)
                                except:
                                    pass

                elif unique_id not in POST_ALERT_IDS and -60 <= air_ts - now_ts <= 60:
                    POST_ALERT_IDS.add(unique_id)
                    if len(POST_ALERT_IDS) > MAX_ALERT_IDS:
                        oldest = next(iter(POST_ALERT_IDS))
                        POST_ALERT_IDS.discard(oldest)
                    text = f"╰► NEW EPISODE RELEASED\n\n<b>✶ {title}</b>\n│ Ep     : {ep}\n│ Status : Just Aired! ✅\n└───────────────"
                    for channel in CHANNEL_IDS:
                        await app.send_message(channel, text, parse_mode=ParseMode.HTML)

        except Exception as e:
            print("Alert Error:", e)

        await asyncio.sleep(5)

# -------- COMMANDS --------
@app.on_message(filters.command("nlink"))
async def generate_link(client, message):
    try:
        msg_id = int(message.command[1])
        output = f"""✅ Ready To Copy :
       
`480p - {BASE_LINK.format(msg_id)} && 720p - {BASE_LINK.format(msg_id+1)} && 1080p - {BASE_LINK.format(msg_id+2)}
HDRip - {BASE_LINK.format(msg_id+3)}`"""
        await message.reply_text(output)
    except:
        await message.reply_text("Usage: /nlink 12345")

@app.on_message(filters.command("today"))
async def today(client, m):
    msg = await m.reply(
        " Today's Schedule:\n\n" + fetch_schedule(0),
        parse_mode=ParseMode.HTML,
        reply_markup=get_buttons("today")
    )
    asyncio.create_task(auto_delete(client, msg.chat.id, msg.id))

@app.on_message(filters.command("tomorrow"))
async def tomorrow(client, m):
    msg = await m.reply(
        " Tomorrow's Schedule:\n\n" + fetch_schedule(1),
        parse_mode=ParseMode.HTML,
        reply_markup=get_buttons("tomorrow")
    )
    asyncio.create_task(auto_delete(client, msg.chat.id, msg.id))

@app.on_message(filters.command("caption"))
async def caption(client, m):
    if len(m.command) < 2:
        await m.reply("Usage: /caption <anime name>\nExample: /caption Dorohedoro Season 2")
        return
    query_text = " ".join(m.command[1:])
    result = fetch_anime_caption(query_text)
    replied = m.reply_to_message
    if replied and replied.photo:
        await client.send_photo(
            chat_id=m.chat.id,
            photo=replied.photo.file_id,
            caption=result,
            parse_mode=ParseMode.HTML
        )
    else:
        await m.reply(result, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("donghua"))
async def donghua(client, m):
    if len(m.command) < 2:
        await m.reply("Usage: /donghua <donghua name>\nExample: /donghua Renegade Immortal")
        return
    query_text = " ".join(m.command[1:])
    result = fetch_donghua_caption(query_text)
    replied = m.reply_to_message
    if replied and replied.photo:
        await client.send_photo(
            chat_id=m.chat.id,
            photo=replied.photo.file_id,
            caption=result,
            parse_mode=ParseMode.HTML
        )
    else:
        await m.reply(result, parse_mode=ParseMode.HTML)


# -------- CALLBACK --------
@app.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    try:
        day = data
        day_offset = 0 if day == "today" else 1
        day_label = "Today's" if day == "today" else "Tomorrow's"
        text = f" {day_label} Schedule:\n\n" + fetch_schedule(day_offset)
        await callback_query.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_buttons(day)
        )
        await callback_query.answer("Updated ✅")
    except Exception as e:
        print("Callback Error:", e)

# -------- MAIN --------
async def main():
    print("Bot Started ✅")
    await app.start()
    asyncio.create_task(auto_airing_alert())
    await idle()

asyncio.run(main())