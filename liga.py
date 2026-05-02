import discord
import os
import logging
import aiohttp
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUMMONER_NAME = os.getenv("RIOT_SUMMONER_NAME")
REGION = os.getenv("RIOT_REGION")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
RIOT_TAGLINE = os.getenv("RIOT_TAGLINE")
MAX_GAMES = 10

PLATFORM_URL = f"https://{REGION}.api.riotgames.com"
REGIONAL_URL = "https://europe.api.riotgames.com"

HEADERS = {"X-Riot-Token": RIOT_API_KEY}

if not RIOT_API_KEY:
    logger.error("CRITICAL: RIOT_API_KEY not found in environment variables!")
else:
    logger.info(f"RIOT_API_KEY loaded: {RIOT_API_KEY[:10]}...")

if not SUMMONER_NAME:
    logger.error("CRITICAL: RIOT_SUMMONER_NAME not found in environment variables!")
else:
    logger.info(f"Summoner name configured: {SUMMONER_NAME}")

if not RIOT_TAGLINE:
    logger.warning("RIOT_TAGLINE not found, using default: EUW")
else:
    logger.info(f"TagLine configured: {RIOT_TAGLINE}")

logger.info(f"Region configured: {REGION}")


@dataclass
class GameStats:
    match_id: str
    champion: str
    queue_type: str
    kills: int
    deaths: int
    assists: int
    win: bool
    game_mode: str
    game_duration: int
    timestamp: int
    items: list
    spells: list
    level: int
    cs: int


def calculate_kda_ratio(kills: int, deaths: int, assists: int) -> str:
    total = kills + assists
    if deaths == 0:
        return "Perfect"
    ratio = total / deaths
    return f"{ratio:.2f}"


async def get_summoner_puuid(
    summoner_name: str, tagline: str, api_key: str
) -> Optional[str]:
    url = (
        f"{REGIONAL_URL}/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tagline}"
    )

    logger.info(f"Fetching PUUID for Riot ID '{summoner_name}#{tagline}' from {url}")

    if not api_key:
        logger.error("RIOT_API_KEY is not set or empty")
        return None

    headers = {"X-Riot-Token": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"Riot Account API response status: {response.status}")

                if response.status == 200:
                    data = await response.json()
                    puuid = data.get("puuid")
                    if puuid:
                        logger.info(f"Successfully fetched PUUID: {puuid[:16]}...")
                    else:
                        logger.error("PUUID not found in API response")
                    return puuid
                else:
                    try:
                        error_body = await response.text()
                        logger.error(
                            f"Riot Account API failed: HTTP {response.status} - {error_body}"
                        )
                    except Exception:
                        logger.error(f"Riot Account API failed: HTTP {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Exception fetching PUUID: {type(e).__name__}: {str(e)}")
        return None


async def get_match_ids(puuid: str, count: int, api_key: str) -> List[str]:
    url = f"{REGIONAL_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"count": min(count, MAX_GAMES)}

    logger.info(f"Fetching {count} match IDs for PUUID {puuid[:16]}...")

    if not api_key:
        logger.error("RIOT_API_KEY is not set or empty")
        return []

    headers = {"X-Riot-Token": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                logger.info(f"Matches API response status: {response.status}")

                if response.status == 200:
                    match_ids = await response.json()
                    logger.info(f"Found {len(match_ids)} matches")
                    return match_ids
                else:
                    try:
                        error_body = await response.text()
                        logger.error(
                            f"Matches API failed: HTTP {response.status} - {error_body}"
                        )
                    except Exception:
                        logger.error(f"Matches API failed: HTTP {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Exception fetching match IDs: {type(e).__name__}: {str(e)}")
        return []


async def get_match_details(match_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    url = f"{REGIONAL_URL}/lol/match/v5/matches/{match_id}"

    logger.info(f"Fetching details for match {match_id}")

    if not api_key:
        logger.error("RIOT_API_KEY is not set or empty")
        return None

    headers = {"X-Riot-Token": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"Match details API response status: {response.status}")

                if response.status == 200:
                    return await response.json()
                else:
                    try:
                        error_body = await response.text()
                        logger.error(
                            f"Match details API failed: HTTP {response.status} - {error_body}"
                        )
                    except Exception:
                        logger.error(
                            f"Match details API failed: HTTP {response.status}"
                        )
                    return None
    except Exception as e:
        logger.error(f"Exception fetching match details: {type(e).__name__}: {str(e)}")
        return None


def parse_match_data(match_data: Dict[str, Any], puuid: str) -> Optional[GameStats]:
    try:
        info = match_data.get("info", {})
        metadata = match_data.get("metadata", {})

        participants = info.get("participants", [])
        player = next((p for p in participants if p.get("puuid") == puuid), None)

        if not player:
            logger.error("Player not found in match participants")
            return None

        queue_id = info.get("queueId", 0)
        queue_type = get_queue_type(queue_id)

        items = [
            player.get("item0"),
            player.get("item1"),
            player.get("item2"),
            player.get("item3"),
            player.get("item4"),
            player.get("item5"),
            player.get("item6"),
        ]

        spells = [
            player.get("summoner1Id"),
            player.get("summoner2Id"),
        ]

        return GameStats(
            match_id=metadata.get("matchId", ""),
            champion=player.get("championName", "Unknown"),
            queue_type=queue_type,
            kills=player.get("kills", 0),
            deaths=player.get("deaths", 0),
            assists=player.get("assists", 0),
            win=player.get("win", False),
            game_mode=get_game_mode(info.get("gameMode", "UNKNOWN")),
            game_duration=info.get("gameDuration", 0),
            timestamp=info.get("gameEndTimestamp", 0),
            items=[item for item in items if item > 0],
            spells=spells,
            level=player.get("champLevel", 1),
            cs=player.get("totalMinionsKilled", 0)
            + player.get("neutralMinionsKilled", 0),
        )
    except Exception as e:
        logger.error(f"Error parsing match data: {str(e)}")
        return None


def get_queue_type(queue_id: int) -> str:
    queue_types = {
        420: "Ranked Solo/Duo",
        440: "Ranked Flex",
        450: "ARAM",
        400: "Normal Draft",
        430: "Blind Pick",
        900: "URF",
        1020: "One vs One",
        1030: "Two vs Two",
    }
    return queue_types.get(queue_id, f"Queue {queue_id}")


def get_game_mode(mode: str) -> str:
    modes = {
        "CLASSIC": "Summoner's Rift",
        "ARAM": "ARAM",
        "URF": "URF",
        "ONEFORALL": "One for All",
        "TUTORIAL": "Tutorial",
    }
    return modes.get(mode, mode)


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"


def create_game_embed(game: GameStats) -> discord.Embed:
    color = 0x00FF00 if game.win else 0xFF0000
    result = "Victory" if game.win else "Defeat"
    emoji = "🟢" if game.win else "🔴"

    embed = discord.Embed(
        title=f"{emoji} {result} - {game.champion}",
        color=color,
        timestamp=datetime.fromtimestamp(game.timestamp / 1000),
    )

    kda_ratio = calculate_kda_ratio(game.kills, game.deaths, game.assists)
    embed.add_field(
        name="KDA",
        value=f"{game.kills}/{game.deaths}/{game.assists} ({kda_ratio})",
        inline=True,
    )

    embed.add_field(name="Queue", value=game.queue_type, inline=True)

    embed.add_field(name="CS", value=game.cs, inline=True)

    embed.add_field(name="Level", value=game.level, inline=True)

    embed.add_field(
        name="Duration", value=format_duration(game.game_duration), inline=True
    )

    items_str = " ".join([f"📦" for _ in game.items])
    if game.items:
        item_icons = ["💎", "🔮", "💍", "🧪", "🛡️", "⚔️", "👢"]
        items_str = " ".join(
            [
                f"{item_icons[i % len(item_icons)]} Item{i + 1}"
                for i in range(len(game.items))
            ]
        )
    else:
        items_str = "No items"
    embed.add_field(name="Items", value=items_str, inline=False)

    embed.set_footer(text=f"Match ID: {game.match_id}")

    return embed


def create_games_embed(games: List[GameStats]) -> discord.Embed:
    if not games:
        return discord.Embed(
            title="No Games Found",
            description="Unable to retrieve game data.",
            color=0xFFA500,
        )

    color = 0x00FF00 if games[0].win else 0xFF0000

    embed = discord.Embed(
        title=f"Last {len(games)} Games - {SUMMONER_NAME}",
        color=color,
        timestamp=datetime.fromtimestamp(games[0].timestamp / 1000)
        if games[0].timestamp
        else None,
    )

    wins = sum(1 for g in games if g.win)
    losses = len(games) - wins

    total_kills = sum(g.kills for g in games)
    total_deaths = sum(g.deaths for g in games)
    total_assists = sum(g.assists for g in games)

    overall_kda = calculate_kda_ratio(total_kills, total_deaths, total_assists)

    embed.add_field(
        name="Summary",
        value=f"Wins: {wins} | Losses: {losses}\nOverall KDA: {total_kills}/{total_deaths}/{total_assists} ({overall_kda})",
        inline=False,
    )

    for i, game in enumerate(games, 1):
        emoji = "✅" if game.win else "❌"
        kda = calculate_kda_ratio(game.kills, game.deaths, game.assists)
        duration = format_duration(game.game_duration)

        game_info = f"{emoji} **{game.champion}** - {game.queue_type}\n"
        game_info += (
            f"KDA: {game.kills}/{game.deaths}/{game.assists} ({kda}) | {duration}"
        )

        embed.add_field(
            name=f"Game {i}",
            value=game_info,
            inline=False,
        )

    embed.set_footer(text=f"Region: {REGION} | Max games: {MAX_GAMES}")

    return embed


async def get_last_game_embed(
    puuid: str, region: str, api_key: str
) -> Optional[discord.Embed]:
    match_ids = await get_match_ids(puuid, 1, api_key)

    if not match_ids:
        logger.error("No match IDs found")
        return None

    match_data = await get_match_details(match_ids[0], api_key)

    if not match_data:
        logger.error("Failed to get match details")
        return None

    game = parse_match_data(match_data, puuid)

    if not game:
        logger.error("Failed to parse match data")
        return None

    return create_game_embed(game)


async def get_last_games_embed(
    puuid: str, count: int, region: str, api_key: str
) -> Optional[discord.Embed]:
    count = min(count, MAX_GAMES)

    logger.info(f"Fetching last {count} games for PUUID {puuid[:16]}...")

    match_ids = await get_match_ids(puuid, count, api_key)

    if not match_ids:
        logger.error("No match IDs found")
        return None

    logger.info(f"Found {len(match_ids)} match IDs, fetching details...")

    games = []
    for match_id in match_ids:
        match_data = await get_match_details(match_id, api_key)
        if match_data:
            game = parse_match_data(match_data, puuid)
            if game:
                games.append(game)
                logger.info(
                    f"Parsed game {len(games)}: {game.champion} - {'Win' if game.win else 'Loss'}"
                )

    if not games:
        logger.error("No games could be parsed")
        return None

    logger.info(f"Successfully parsed {len(games)} games, creating embed...")
    return create_games_embed(games)


async def check_and_post_game_stats(client):
    logger.info("Starting LoL stats check...")

    try:
        puuid = await get_summoner_puuid(SUMMONER_NAME, RIOT_TAGLINE, RIOT_API_KEY)
        if not puuid:
            logger.error("Could not fetch summoner PUUID for stats check")
            return

        logger.info(f"Fetched PUUID: {puuid[:16]}...")

        match_ids = await get_match_ids(puuid, 1, RIOT_API_KEY)
        if not match_ids:
            logger.warning("No recent matches found")
            return

        last_match_id = match_ids[0]
        logger.info(f"Last match ID: {last_match_id}")

        last_game_file = "last_lol_game.txt"

        try:
            with open(last_game_file, "r") as f:
                stored_match_id = f.read().strip()
            logger.info(f"Stored match ID: {stored_match_id}")
        except FileNotFoundError:
            stored_match_id = None
            logger.info("No stored match ID found (first run)")

        if last_match_id != stored_match_id:
            logger.info(f"New match detected: {last_match_id}")
            match_data = await get_match_details(last_match_id, RIOT_API_KEY)
            if match_data:
                game = parse_match_data(match_data, puuid)
                if game:
                    logger.info(
                        f"Parsed game: {game.champion} - {'Win' if game.win else 'Loss'}"
                    )
                    embed = create_game_embed(game)

                    channel_ids = [
                        os.getenv("DISCORD_CHANNEL_ID6"),
                        os.getenv("DISCORD_CHANNEL_ID7"),
                    ]
                    channel_ids = [cid for cid in channel_ids if cid is not None]

                    posted = False
                    for channel_id in channel_ids:
                        channel = client.get_channel(int(channel_id))
                        if channel:
                            await channel.send(embed=embed)
                            logger.info(
                                f"Posted LoL game stats to channel {channel_id} for match {last_match_id}"
                            )
                            posted = True
                        else:
                            logger.warning(f"Discord channel {channel_id} not found")

                    if posted:
                        logger.info(f"Posted LoL game stats for match {last_match_id}")
                    else:
                        logger.warning("No Discord channels available for posting")

                    with open(last_game_file, "w") as f:
                        f.write(last_match_id)
                    logger.info(f"Updated stored match ID to {last_match_id}")
                else:
                    logger.error("Failed to parse game data")
            else:
                logger.error("Failed to get match details")
        else:
            logger.info("No new matches since last check")
    except Exception as e:
        logger.error(
            f"Error in check_and_post_game_stats: {type(e).__name__}: {str(e)}"
        )
