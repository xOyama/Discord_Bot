import os
import logging
import asyncio
from datetime import datetime, timezone
from rustplus import RustSocket, ServerDetails, RustMarker, exceptions

rust_socket = None
previous_team_state = {}
small_oil_rig_pos = None
large_oil_rig_pos = None
last_small_taken_time = None
last_large_taken_time = None
current_small_markers = set()
current_large_markers = set()
map_size = 4500
grid_size = 150
total_afk_seconds = 0
afk_start_time = None

def int_to_column_letter(n):
	string = ""
	while n > 0:
		n, remainder = divmod(n - 1, 26)
		string = chr(65 + remainder) + string
	return string

async def connect_rust():
	global rust_socket, small_oil_rig_pos, large_oil_rig_pos
	try:
		server_details = ServerDetails(
			os.getenv("RUST_SERVER_IP"),
			int(os.getenv("RUST_SERVER_PORT")),
			int(os.getenv("STEAM_ID")),
			int(os.getenv("PLAYERTOKEN"))
		)
		rust_socket = RustSocket(server_details)
		await rust_socket.connect()
		logging.info("✅ Connected to Rust server")

		map_info = await rust_socket.get_map_info()
		print("All monuments:")
		for monument in map_info.monuments:
			print(f'{monument.token}: X: {monument.x:.2f}, Y: {monument.y:.2f}')
	except Exception as e:
			logging.error(f"❌ Unexpected error in connect_rust: {str(e)}")

def print_oil_rigs():
	global small_oil_rig_pos, large_oil_rig_pos
	if small_oil_rig_pos:
		print(f'Small oil rig @ {small_oil_rig_pos}')
	if large_oil_rig_pos:
		print(f'Large oil rig @ {large_oil_rig_pos}')
	if not small_oil_rig_pos and not large_oil_rig_pos:
		print("No oil rigs found")

async def track_player_inactivity(steam_id, client):
	global total_afk_seconds, afk_start_time
	last_position = None
	last_move_time = None
	while True:
		try:
			current_team = await rust_socket.get_team_info()
			member = next((m for m in current_team.members if m.steam_id == steam_id), None)
			if not member:
				logging.warning(f"Player {steam_id} not found in team")
				await asyncio.sleep(5)
				continue
			current_pos = (member.x, member.y)
			current_time = datetime.now(timezone.utc)
			if last_position != current_pos:
				if afk_start_time:
					total_afk_seconds += (current_time - afk_start_time).total_seconds()
					afk_start_time = None
				last_position = current_pos
				last_move_time = current_time
			else:
				if not afk_start_time:
					afk_start_time = current_time
				if afk_start_time and (current_time - afk_start_time).total_seconds() >= 5:
					grid = world_position_to_grid(member.x, member.y)
					afk_duration = int((current_time - afk_start_time).total_seconds())
					message = f"{member.name} has not moved for {afk_duration} seconds at grid {grid}"
					channel = client.get_channel(int(os.getenv("DISCORD_CHANNEL_ID5")))
					await channel.send(message)
					await rust_socket.send_team_message(message)
			await asyncio.sleep(5)
		except Exception as e:
			await asyncio.sleep(5)

def get_afk_time():
	global total_afk_seconds
	hours = total_afk_seconds // 3600
	mins = (total_afk_seconds % 3600) // 60
	secs = total_afk_seconds % 60
	parts = []
	if hours > 0:
		parts.append(f"{int(hours)} Hours")
	if mins > 0:
		parts.append(f"{int(mins)} Mins")
	if secs > 0 or not parts:
		parts.append(f"{int(secs)} Secs")
	return "he's been afk for " + " ".join(parts)

async def handle_afk_message_command(message):
	await message.channel.send(get_afk_time())

async def handle_afk_slash_command(interaction):
	await interaction.response.send_message(get_afk_time())

async def listen_rust_chat(client):
	while True:
		try:
			chat_response = await rust_socket.get_team_chat()

			if chat_response:
				latest_msg = chat_response[-1].message.lower()
				if "!time" in latest_msg:
					await handle_rust_time_command(client)
				elif "!afk" in latest_msg:
					await handle_rust_afk_command(client)

			await asyncio.sleep(2)

		except exceptions.ClientNotConnectedError:
			logging.warning("Lost connection to Rust server, reconnecting...")
			await connect_rust()
		except exceptions.RequestError as e:
			logging.error(f"Rust API request failed: {str(e)}")
			await asyncio.sleep(5)
		except Exception as e:
			logging.error(f"Unexpected error: {str(e)}")
			await asyncio.sleep(5)

async def monitor_team_status(client):
	global previous_team_state
	while True:
		try:
			current_team = await rust_socket.get_team_info()
			current_state = {member.steam_id: member for member in current_team.members}

			for steam_id, member in current_state.items():
				prev_member = previous_team_state.get(steam_id)

				if prev_member and prev_member.is_alive and not member.is_alive:
					await handle_team_death(member, client)

			previous_team_state = {m.steam_id: m for m in current_team.members}
			await asyncio.sleep(5)

		except exceptions.ClientNotConnectedError:
			logging.warning("Lost connection to Rust server, reconnecting...")
			await connect_rust()
			await asyncio.sleep(5)
		except Exception as e:
			logging.error(f"Error in team monitor: {str(e)}")
			await asyncio.sleep(10)

async def handle_team_death(victim, client):
	try:
		x, y = victim.x, victim.y
		logging.info(f"Death coordinates: x={x}, y={y}, map_size={map_size}")
		grid = world_position_to_grid(x, y)
		death_message = f"{victim.name} died at grid {grid}"
		channel = client.get_channel(int(os.getenv("DISCORD_CHANNEL_ID5")))
		await channel.send(death_message)
		await rust_socket.send_team_message(death_message)
	except Exception as e:
		logging.error(f"Error handling death: {str(e)}")

def world_position_to_grid(x, y):
	max_grids = int(map_size / grid_size)

	c = int(x // grid_size)
	column_letter = int_to_column_letter(c + 1)

	r = int(y // grid_size)
	row_number = max_grids - r

	return f"{column_letter}{row_number}"

async def handle_rust_time_command(client):
	try:
		rust_time = (await rust_socket.get_time()).time
		message = f"🕒 Current server time is: {rust_time}"

		await rust_socket.send_team_message(message)

		channel = client.get_channel(int(os.getenv("DISCORD_CHANNEL_ID5")))
		await channel.send(f"From in-game command:\n{message}")

	except Exception as e:
		logging.error(f"Game time handler error: {str(e)}")

async def handle_rust_afk_command(client):
	try:
		afk_message = get_afk_time()

		await rust_socket.send_team_message(afk_message)

		channel = client.get_channel(int(os.getenv("DISCORD_CHANNEL_ID5")))
		await channel.send(f"From in-game command:\n{afk_message}")

	except Exception as e:
		logging.error(f"AFK handler error: {str(e)}")
