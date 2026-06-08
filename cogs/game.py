import discord
from discord.ext import commands

from config import game
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
        game.reset_state()
        game.text_channel = ctx.channel
        game.host = ctx.author
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(), view=view)

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
