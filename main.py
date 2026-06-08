import discord, os
from discord.ext import commands

# 環境変数チェック
if not os.getenv("DISCORD_BOT_TOKEN"):
    raise ValueError("DISCORD_BOT_TOKEN 環境変数が設定されていません")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook(): 
    await bot.load_extension("cogs.game")
    await bot.load_extension("cogs.item")
    await bot.load_extension("cogs.phases")
    await bot.load_extension("cogs.discussion")
    await bot.load_extension("cogs.voting")
    await bot.load_extension("cogs.night")

@bot.event
async def on_ready():
    print(f"🤖 ログインしました: {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
