async def handle_twitter_links(message):
	content_lower = message.content.lower()

	if 'fxtwitter.com' in content_lower or 'vxtwitter.com' in content_lower or 'fixvx.com' in content_lower:
		return
	else:
		new_content = message.content.replace('twitter.com', 'vxtwitter.com').replace('x.com', 'fixvx.com')
		await message.channel.send(f'{new_content}\nTweet was sent by: "{message.author}"')
		await message.delete()
