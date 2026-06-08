import discord, json, os
from discord.ext import commands

from config import get_game
from views import RecruitView
import channels

# アイテムシステム関連のインポート
from cogs.item import reset_items

# 分割したフェーズのインポート
from cogs.phases import execute_game_start, check_game_over
from cogs.night import start_night, process_night_results
from cogs.discussion import start_discussion
from cogs.voting import start_voting

# 役職インポート
from roles.werewolf import Werewolf
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.serial_killer import SerialKiller
from roles.villager import Villager

class GameCog(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    # 💡 コマンド名を「game_setup」に変更し、Discord.pyのシステム用setup関数との衝突を防止
    # サーバー上での入力は「!game_setup」になります
    @commands.command(name="game_setup")
    @commands.has_permissions(administrator=True)
    async def game_setup(self, ctx):
        game = get_game(ctx.guild.id)
        game.reset_state()
        game.text_channel = ctx.channel
        game.host = ctx.author
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(ctx.guild.id), view=view)

    @commands.command(name="game_resume")
    @commands.has_permissions(administrator=True)
    async def game_resume(self, ctx):
        """保存されたデータからゲームを復旧する"""
        file_path = f"data/game_{ctx.guild.id}.json"
        if not os.path.exists(file_path):
            return await ctx.send("⚠️ 保存されたゲームデータが見つかりません。")
        
        game = get_game(ctx.guild.id)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        game.load_from_dict(data, ctx.guild)
        await ctx.send(f"✅ {game.day_count}日目の状態からゲームを復旧しました。")

    # 分割したメソッドをバインド
    execute_game_start = execute_game_start
    start_night = start_night
    process_night_results = process_night_results
    start_discussion = start_discussion
    start_voting = start_voting
    check_game_over = check_game_over


# 💡 Discord.pyの拡張ロードシステム用関数（これで競合しません）
async def setup(bot): 
    await bot.add_cog(GameCog(bot))
