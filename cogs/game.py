import discord, json, os
from discord.ext import commands

from config import get_game, get_leaderboard
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

    @commands.command(name="game_stats")
    async def game_stats(self, ctx):
        """通算勝利数ランキングを表示する"""
        stats = get_leaderboard(ctx.guild.id)
        if not stats:
            return await ctx.send("📊 まだ統計データがありません。ゲームを完了させてください！")

        # スコア順にソート
        # (村人勝 + 人狼勝 + SK勝) の合計が多い順
        sorted_stats = sorted(
            stats.items(), 
            key=lambda x: (x[1].get("human_win", 0) + x[1].get("wolf_win", 0) + x[1].get("sk_win", 0)), 
            reverse=True
        )
        
        embed = discord.Embed(title="🏆 人狼ゲーム 通算戦績ランキング", color=discord.Color.gold())
        ranking_text = ""
        for i, (uid_str, s) in enumerate(sorted_stats[:10], 1): # 上位10名
            member = ctx.guild.get_member(int(uid_str))
            name = member.display_name if member else f"退会したユーザー({uid_str})"
            
            total_wins = s["human_win"] + s["wolf_win"] + s["sk_win"]
            survive_rate = (s["survived_count"] / s["total"] * 100) if s["total"] > 0 else 0
            
            ranking_text += (f"{i}位: **{name}**\n"
                            f"　 🏆計{total_wins}勝 (村:{s['human_win']} 狼:{s['wolf_win']} SK:{s['sk_win']})\n"
                            f"　 📈生存率: {survive_rate:.1f}% ({s['total']}戦)\n")
        
        embed.description = ranking_text
        await ctx.send(embed=embed)

    @commands.command(name="msgdel")
    @commands.has_permissions(manage_messages=True)
    async def msgdel(self, ctx, amount: int):
        """指定した件数のメッセージを削除します。例: !msgdel 10"""
        # コマンド自体のメッセージも含めて削除するため、指定数+1を削除します
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 {len(deleted)-1}件のメッセージを削除しました。", delete_after=5)

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
