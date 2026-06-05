# main.py
import discord
from discord.ext import commands
import os
import sys
from config import game

# 1. 権限（インテント）の設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 2. 初期セットアップ（Cogの読み込みはここで行うのが最も安全です）
@bot.event
async def setup_hook():
    try:
        # cogs/game.py を読み込み
        await bot.load_extension("cogs.game")
        print("✅ GameCog(cogs/game.py) を正常に読み込みました。")
    except Exception as e:
        print(f"❌ Cogの読み込みに失敗しました: {e}")

# 3. 起動完了時の処理（ここで古い幽霊コマンドを掃除します）
@bot.event
async def on_ready():
    print(f"================================")
    print(f"🤖 ログイン成功: {bot.user.name}")
    print(f"================================")
    
    try:
        # Discord側に残っている古いスラッシュコマンド（/werewolf_setup など）をクレンジング
        print("🔄 古いコマンドの同期・削除を実行中...")
        await bot.tree.sync()
        print("✨ コマンドの同期が完了しました！エラーは解消されます。")
    except Exception as e:
        print(f"⚠️ コマンド同期中にエラーが発生しました: {e}")

# 4. 【人狼同士のDMチャット転送ロジック】（元の処理を完全キープ）
@bot.event
async def on_message(message):
    # Bot自身の発言やサーバー内での発言はスルー
    if message.author.bot or message.guild is not None:
        await bot.process_commands(message)
        return

    # ゲーム中、かつ送信者が生きている場合
    if game.is_playing and message.author in game.alive_players:
        sender_role = game.roles.get(message.author)
        
        # 送信者が「人狼」の役職データを持っていれば、他の生存している人狼のDMへ転送
        if sender_role and sender_role.name == "人狼":
            for member in game.alive_players:
                if member != message.author:
                    target_role = game.roles.get(member)
                    if target_role and target_role.name == "人狼":
                        try:
                            await member.send(f"💬 [人狼チャット] **{message.author.display_name}**: {message.content}")
                        except discord.Forbidden:
                            pass

    await bot.process_commands(message)

# 5. トークンを読み込んで起動
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ エラー: 環境変数 'DISCORD_BOT_TOKEN' が設定されていません。")
