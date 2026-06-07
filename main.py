import discord, os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook(): 
    await bot.load_extension("cogs.game")
    await bot.load_extension("cogs.item")

@bot.event
async def on_ready():
    print(f"🤖 ログインしました: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
