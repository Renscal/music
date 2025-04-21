
import os
import asyncio
import discord
from discord.ext import commands
import yt_dlp as youtube_dl

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'extract_flat': False,
}
ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
loop_states = {}  # guild_id -> loop state

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def play(ctx, url):
    if ctx.author.voice is None:
        await ctx.send("You must be connected to a voice channel to play music.")
        return

    voice_client = ctx.voice_client
    if voice_client is None:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        guild_id = ctx.guild.id
        loop_states[guild_id] = False  # default loop state

        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            elif loop_states.get(guild_id, False):
                coro = replay(ctx, player.url)
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"Replay error: {e}")
            else:
                coro = voice_client.disconnect()
                asyncio.run_coroutine_threadsafe(coro, bot.loop)

        voice_client.play(player, after=after_playing)
        await ctx.send(f'Now playing: {player.title}')

async def replay(ctx, url):
    player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
    ctx.voice_client.play(player, after=lambda e: print(f'Loop error: {e}') if e else None)

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        loop_states[ctx.guild.id] = False
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send('Stopped the music and left the voice channel.')
    else:
        await ctx.send('I am not playing anything.')

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send('Paused the music.')
    else:
        await ctx.send('Nothing is playing.')

@bot.command()
async def loop(ctx):
    current = loop_states.get(ctx.guild.id, False)
    loop_states[ctx.guild.id] = not current
    await ctx.send(f'Looping is now {"enabled" if not current else "disabled"}.')

# Securely get token from environment
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN environment variable not set.")

bot.run(TOKEN)
