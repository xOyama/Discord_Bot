import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import logging
from datetime import datetime, timezone
from discord.ext import tasks
import asyncio

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
youtube = build('youtube', "v3", developerKey=YOUTUBE_API_KEY)

LATEST_VIDEOS_FILE = 'latest_videos.json'

YOUTUBE_CHANNELS = {
	"Ryan": {
		"channel_id": "UCEnBjBVH6NuvY5RWj5C8PrA",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID"))
			}
		]
	},
	"OnePeg": {
		"channel_id": "UCFyX27M0e8NW0kysAsY1Grg",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID"))
			}
		]
	},
	"PoE": {
		"channel_id": "UCA7X5unt1JrIiVReQDUbl_A",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD2")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID2"))
			}
		]
	},
	"Ziggy": {
		"channel_id": "UC4mLMb49hqk4y9lVFtfanlg",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD2")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID2"))
			}
		]
	},
	"Rhykker": {
		"channel_id": "UCRl31PWkfF0a3j3hiDRaCGA",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD2")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID3"))
			}
		]
	},
	"Rivals": {
		"channel_id": "UCWzmOSSiSPbVnVu3ZAyDx2w",
		"notify_channels": [
			{
				"guild_id": int(os.getenv("GUILD")),
				"channel_id": int(os.getenv("DISCORD_CHANNEL_ID4"))
			}
		]
	},
}

def load_latest_videos_data():
	if os.path.exists(LATEST_VIDEOS_FILE):
		try:
			with open(LATEST_VIDEOS_FILE, 'r') as f:
				return json.load(f)
		except json.JSONDecodeError:
			logging.error("Error reading JSON file. It might be empty or incorrectly formatted.")
	return {}

def save_latest_videos_data(data):
	try:
		with open(LATEST_VIDEOS_FILE, 'w') as f:
			json.dump(data, f)
		logging.info(f"Successfully saved data to {LATEST_VIDEOS_FILE}")
		return True
	except IOError as e:
		logging.error(f"Failed to save data to {LATEST_VIDEOS_FILE}: {e}")
		return False
	except Exception as e:
		logging.error(f"Unexpected error while saving data: {e}")
		return False

async def get_uploads_playlist_id(channel_id):
	try:
		channel_response = youtube.channels().list(
			part="contentDetails",
			id=channel_id
		).execute()

		if not channel_response.get('items'):
			logging.error(f"No channel found for ID {channel_id}")
			return None

		uploads_playlist = channel_response['items'][0]['contentDetails']['relatedPlaylists'].get('uploads')

		if not uploads_playlist:
			logging.warning(f"No uploads playlist found for channel {channel_id}")
			return None

		return uploads_playlist

	except HttpError as e:
		if e.resp.status == 404:
			logging.error(f"Channel not found for ID {channel_id}")
		elif e.resp.status == 403:
			logging.error(f"Access forbidden for channel {channel_id}. Check API key and permissions.")
		else:
			logging.error(f"HTTP error occurred while fetching uploads playlist ID for channel {channel_id}: {e}")
		return None
	except KeyError as e:
		logging.error(f"Unexpected response structure for channel {channel_id}: {e}")
		return None
	except Exception as e:
		logging.error(f"Unexpected error fetching uploads playlist ID for channel {channel_id}: {e}")
		return None

async def get_latest_video(channel_name, channel_id, channel_data):
	current_time = datetime.now(timezone.utc)
	logging.info(f"Checking for new videos on channel {channel_name} . Last check: {channel_data.get('last_check_time')}, Current time: {current_time}")
	logging.info(f"---------------------------------------------------------------------------------------------------------------------------------------------------")

	uploads_playlist_id = channel_data.get('uploads_playlist_id') or await get_uploads_playlist_id(channel_id)
	if not uploads_playlist_id:
		logging.error(f"Failed to get uploads playlist ID for channel {channel_name} ({channel_id})")
		return None

	try:
		playlist_response = youtube.playlistItems().list(
			part="snippet",
			playlistId=uploads_playlist_id,
			maxResults=5
		).execute()

		for item in playlist_response['items']:
			video = item['snippet']
			video_id = video['resourceId']['videoId']

			video_response = youtube.videos().list(
				part="snippet,status",
				id=video_id
			).execute()

			if not video_response['items']:
				continue

			video_details = video_response['items'][0]
			publish_time = video_details['snippet']['publishedAt']

			if video_details['snippet'].get('liveBroadcastContent') != 'live':
				logging.info(f"Latest video for channel {channel_name}, ID: {video_id}, Publish time: {publish_time}")
				logging.info(f"---------------------------------------------------------------------------------------------------------------------------------------------------")

				if video_id != channel_data.get('latest_video_id') and publish_time > channel_data.get('last_check_time', '1970-01-01T00:00:00Z'):
					return {
						'channel_name': channel_name,
						'channel_id': channel_id,
						'video_id': video_id,
						'publish_time': publish_time,
						'uploads_playlist_id': uploads_playlist_id
					}
				break

	except HttpError as e:
		logging.error(f"An HTTP error occurred for channel {channel_name} ({channel_id}): {e}")
	except Exception as e:
		logging.error(f"An error occurred while fetching video for channel {channel_name} ({channel_id}): {e}")

	return None

@tasks.loop(minutes=5)
async def check_for_new_videos(client):
	logging.info("Starting check for new videos on all channels in 3..., 2..., 1...\n")
	data = load_latest_videos_data()

	for channel_name, channel_info in YOUTUBE_CHANNELS.items():
		channel_id = channel_info["channel_id"]
		channel_data = data.get(channel_id, {})
		new_video = await get_latest_video(channel_name, channel_id, channel_data)

		if new_video:
			for notify_channel in channel_info["notify_channels"]:
				guild = client.get_guild(notify_channel["guild_id"])
				if guild:
					channel = guild.get_channel(notify_channel["channel_id"])
					if channel:
						await channel.send(f"New video uploaded on {new_video['channel_name']}'s channel: https://www.youtube.com/watch?v={new_video['video_id']}")
					else:
						logging.error(f"Could not find channel {notify_channel['channel_id']} in guild {notify_channel['guild_id']}")
				else:
					logging.error(f"Could not find guild {notify_channel['guild_id']}")

			data[channel_id] = {
				'latest_video_id': new_video['video_id'],
				'last_check_time': new_video['publish_time'],
				'uploads_playlist_id': new_video['uploads_playlist_id']
			}
		else:
			data[channel_id] = {
				**channel_data,
				'last_check_time': datetime.now(timezone.utc).isoformat()
			}

		await asyncio.sleep(5)

	save_latest_videos_data(data)
	logging.info("Finished check for new videos on all channels")
