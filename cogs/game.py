import discord, json, os
from discord.ext import commands

from config import get_game, get_leaderboard
from views import RecruitView
import channels

# アイテムシステム関連のインポート
from cogs.item import reset_items

# 分割したフェーズのインポート
from cogs.phases import execute_game_start, check_game_over, force_stop_game
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
        await ctx.send(embed=discord.Embed(description=f"✅ {game.day_count}日目の状態からゲームを復旧しました。", color=discord.Color.green()))

    @commands.command(name="game_stats")
    async def game_stats(self, ctx):
        """通算勝利数ランキングを表示する"""
        stats = get_leaderboard(ctx.guild.id)
        if not stats:
            return await ctx.send(embed=discord.Embed(description="📊 まだ統計データがありません。ゲームを完了させてください！", color=discord.Color.orange()))

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
    async def msgdel(self, ctx, amount: int):
        """指定した件数のメッセージを削除します。例: !msgdel 10"""
        if ctx.guild:
            # サーバー内での処理
            game = get_game(ctx.guild.id)
            # ゲームが進行中の場合のみ、管理者権限またはホスト権限をチェックする
            if game.is_playing:
                is_admin = ctx.author.guild_permissions.manage_messages
                is_host = (game.host and ctx.author.id == game.host.id)
                if not (is_admin or is_host):
                    return await ctx.send("❌ ゲーム進行中は、混乱を防ぐため管理者またはホストのみがメッセージを削除できます。", delete_after=5)

            # コマンド自体のメッセージも含めて削除するため、指定数+1を削除します
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(embed=discord.Embed(description=f"🧹 {len(deleted)-1}件のメッセージを削除しました。", color=discord.Color.blue()), delete_after=5)
        else:
            # DM内での処理 (purgeが使えないため1つずつ削除)
            count = 0
            async for msg in ctx.channel.history(limit=amount + 1):
                if msg.author == self.bot.user:
                    try:
                        await msg.delete()
                        count += 1
                    except:
                        pass
            await ctx.send(embed=discord.Embed(description=f"🧹 DM内のボットのメッセージを {count} 件削除しました。", color=discord.Color.blue()), delete_after=5)

    @commands.command(name="game_stop")
    @commands.guild_only()
    async def game_stop(self, ctx):
        """現在進行中のゲームを強制終了し、チャンネルとデータを削除します"""
        game = get_game(ctx.guild.id)
        if not game.is_playing:
            return await ctx.send(embed=discord.Embed(description="⚠️ 現在進行中のゲームはありません。", color=discord.Color.orange()))

        # 権限チェック：主催者または管理者のみ
        is_admin = ctx.author.guild_permissions.administrator
        is_host = (game.host and ctx.author.id == game.host.id)
        if not (is_admin or is_host):
            return await ctx.send(embed=discord.Embed(description="❌ ゲームを強制終了できるのは、主催者または管理者のみです。", color=discord.Color.red()), delete_after=5)

        await ctx.send(embed=discord.Embed(description="🛑 ゲームを強制終了します。リソースを解放しています...", color=discord.Color.dark_red()))
        await self.force_stop_game(ctx.channel)

    @msgdel.error
    async def msgdel_error(self, ctx, error):
        """msgdelコマンド専用のエラーハンドリング"""
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=discord.Embed(description="❌ このコマンドはサーバー内でのみ使用できます。", color=discord.Color.red()), delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(description="❌ 削除する件数を指定してください。例: !msgdel 10", color=discord.Color.orange()), delete_after=5)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=discord.Embed(description="❌ あなたには「メッセージの管理」権限がないため、このコマンドは実行できません。", color=discord.Color.red()), delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=discord.Embed(description="❌ 削除する件数は数字で指定してください。例: !msgdel 10", color=discord.Color.orange()), delete_after=5)
        else:
            await ctx.send(embed=discord.Embed(description=f"❌ 予期せぬエラーが発生しました: {error}", color=discord.Color.red()), delete_after=5)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """ボイス状態を監視し、ロック中の勝手なミュート解除を防止する"""
        if not member.guild: return
        game = get_game(member.guild.id)

        # 【重要】ゲームが実行されていないのにサーバーミュートされている場合、自動で解除する（事後クリーンアップ）
        if not game.is_playing:
            if after.channel and after.mute:
                try:
                    await member.edit(mute=False)
                except:
                    pass
            return

        if member in game.alive_players:
            # 🌙 夜間・投票時間のロック（マイクを強制的にミュート）
            if getattr(game, 'vc_locked', False):
                if not after.mute:
                    try:
                        await member.edit(mute=True)
                    except discord.Forbidden:
                        print(f"❌ 権限不足: {member.display_name} のVCミュート強制に失敗しました。Botに「メンバーをミュート」権限があるか確認してください。")
                    except Exception: pass
            # ☀️ 昼間のアイテム効果（マイクのみ強制オフ）
            elif member.id in game.silenced_players:
                # マイクがオンになった場合、強制的に「ミュート」に戻す
                if not after.mute:
                    try:
                        await member.edit(mute=True)
                    except discord.Forbidden:
                        print(f"❌ 権限不足: {member.display_name} の沈黙の御札によるVCミュート強制に失敗しました。Botに「メンバーをミュート」権限があるか確認してください。")
                    except Exception: pass
        # 👻 死亡者が墓場VCにいる場合は、常に喋れるように（ミュートを自動解除）
        elif game.is_playing and game.dead_vc and after.channel == game.dead_vc:
            if after.mute:
                try:
                    await member.edit(mute=False)
                except discord.Forbidden:
                    print(f"❌ 権限不足: {member.display_name} の墓場VCでのミュート解除に失敗しました。Botに「メンバーをミュート」権限があるか確認してください。")
                except Exception: pass

    # 分割したメソッドをバインド
    execute_game_start = execute_game_start
    start_night = start_night
    process_night_results = process_night_results
    start_discussion = start_discussion
    start_voting = start_voting
    check_game_over = check_game_over
    force_stop_game = force_stop_game


# 💡 Discord.pyの拡張ロードシステム用関数（これで競合しません）
async def setup(bot): 
    await bot.add_cog(GameCog(bot))
