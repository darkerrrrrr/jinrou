import discord, os
from discord.ext import commands
from config import game

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True # 💡 VCのミュート制御（沈黙の御札など）に必要なため追加

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook(): 
    # 💡 進行用の game と、新システムの item を両方確実にロードします
    await bot.load_extension("cogs.game")
    await bot.load_extension("cogs.item")

@bot.event
async def on_ready():
    print(f"🤖 ログインしました: {bot.user.name} (ID: {bot.user.id})")
    print("─── アイテム人狼Bot 起動完了 ───")

@bot.event
async def on_message(message):
    # Bot自身の発言、またはサーバー内の公開チャンネルでの発言は転送しない
    if message.author.bot or message.guild:
        await bot.process_commands(message)
        return
        
    # ゲーム中、かつ発言者が「生きているプレイヤー」の場合のみ判定
    if game.is_playing and message.author in game.alive_players:
        role = game.roles.get(message.author)
        
        # 発言者が「人狼」だった場合、他の生きている人狼プレイヤーのDMへ綺麗に整形して転送
        if role and role.name == "人狼":
            for member in game.alive_players:
                # 自分以外の「人狼」プレイヤーに送る
                if member != message.author and game.roles.get(member).name == "人狼":
                    try: 
                        # 太字で「誰が言ったか」をはっきりさせ、メッセージを挟み込みます
                        await member.send(f"💬 **[人狼チャット] {message.author.display_name}**: {message.content}")
                    except: 
                        pass
                        
    await bot.process_commands(message)

# 環境変数からトークンを読み込んで起動
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
