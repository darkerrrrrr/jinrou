import discord, os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True # VCのミュート制御（沈黙の御札など）に必要なため追加

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook(): 
    # 進行用の game と、新システムの item を両方確実にロードします
    await bot.load_extension("cogs.game")
    await bot.load_extension("cogs.item")

@bot.event
async def on_ready():
    print(f"🤖 ログインしました: {bot.user.name} (ID: {bot.user.id})")
    print("─── アイテム人狼Bot 起動完了 ───")

@bot.event
async def on_message(message):
    # Bot自身の発言は無視
    if message.author.bot:
        return

    # コマンド（!game_setup や DMでの !use_crystal などのアクション）を正常に実行するための処理
    await bot.process_commands(message)

# 環境変数からトークンを読み込んで起動
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
