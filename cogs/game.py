import discord
from discord.ext import commands
import asyncio
import random
from collections import Counter
from config import game
from views import RecruitView
from discord.ui import View, Select

# 各個別役職ファイルのインポート
from roles.wolf import Werewolf
from roles.serial_killer import SerialKiller
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.villager import Villager

class GameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cleanup_game_environment(self):
        """【自動掃除】作成したカテゴリとチャンネルを全て削除する"""
        if hasattr(game, 'game_category'):
            for channel in game.game_category.channels:
                await channel.delete()
            await game.game_category.delete()
            # 終了処理後のクリーンアップ
            delattr(game, 'game_category')
            game.log_channel = None
            game.dead_channel = None

    async def mute_all_alive(self, mute_status: bool, reason: str):
        for member in game.alive_players:
            if member.voice and member.voice.channel:
                try: await member.edit(mute=mute_status, reason=reason)
                except: pass

    async def handle_death(self, member: discord.Member):
        if member in game.alive_players:
            game.alive_players.remove(member)
            try: await member.edit(nick=f"[死亡] {member.display_name}")
            except: pass

            # 霊界VCへの移動（ゲームカテゴリ内のVCを探す）
            if member.voice and member.voice.channel and hasattr(game, 'game_category'):
                reikai_vc = next((vc for vc in game.game_category.voice_channels if "霊界" in vc.name), None)
                if reikai_vc:
                    await member.edit(mute=False, voice_channel=reikai_vc)
            
            if game.dead_channel:
                await game.dead_channel.set_permissions(member, read_messages=True, send_messages=True)
                await game.dead_channel.send(f"👻 {member.mention} さんが霊界へ送られました。")

            await game.log_channel.send(f"【死亡通知】 {member.mention} さんが死亡しました。")

    def calc_night_result(self):
        killed, protected, sk_killed = None, None, None
        for actor, target in game.actions.items():
            role = game.roles.get(actor)
            if role and role.name == "狩人": protected = target
            if role and role.name == "人狼" and target != protected: killed = target
            if role and role.name == "シリアルキラー": sk_killed = target
        return sk_killed if sk_killed else killed

    async def run_game_loop(self):
        day_count = 0
        while game.is_playing:
            # --- 朝フェーズ ---
            if day_count == 0:
                await game.log_channel.send("🌅 【0日目：朝】顔合わせ時間（30秒）")
                await asyncio.sleep(30)
            else:
                await game.log_channel.send(f"🌅 【{day_count}日目：朝】昨晩の結果発表...")
                # ... (既存の霊媒師・死亡処理ロジックをそのまま使用)
                killed_player = self.calc_night_result()
                if killed_player and day_count > 1: await self.handle_death(killed_player)
                
                game.actions.clear()
                winner = game.check_victory()
                if winner:
                    await self.mute_all_alive(False, "終了")
                    await game.log_channel.send(f"🏁 ゲーム終了: {winner}\n5秒後にチャンネルを自動で削除します！")
                    await asyncio.sleep(5)
                    await self.cleanup_game_environment()
                    game.is_playing = False
                    break
                await asyncio.sleep(game.morning_time)
                # ... (議論・投票フェーズはあなたの既存のコードをそのままここに置いてください)

            # --- 夜フェーズ ---
            await self.mute_all_alive(True, "夜")
            # ... (夜の行動ロジックをそのままここに置いてください)
            day_count += 1

    @commands.command()
    async def recruit(self, ctx):
        if game.is_playing: return await ctx.send("進行中です。")
        game.players = []
        game.roles.clear()
        view = RecruitView()
        await ctx.send(embed=view.create_recruit_embed(), view=view)

    @commands.command()
    async def start_game(self, ctx):
        if len(game.players) < 3: return await ctx.send("3人以上で開始してください。")

        # 【自動構築】新しいカテゴリとチャンネルを作成
        guild = ctx.guild
        category = await guild.create_category("🐺 人狼ゲーム")
        game.game_category = category
        
        game.log_channel = await guild.create_text_channel("進行ログ", category=category)
        await guild.create_voice_channel("議論用ボイス", category=category)
        await guild.create_voice_channel("霊界ボイス", category=category)
        
        # 霊界チャット（人狼以外は見えない）
        game.dead_channel = await guild.create_text_channel(
            "霊界チャット", category=category,
            overwrites={guild.default_role: discord.PermissionOverwrite(read_messages=False)}
        )

        # 役職割り当て等のロジック
        game.is_playing = True
        game.alive_players = game.players.copy()
        # ... (あなたの役職配布ロジックをここに置いてください)
        
        await game.log_channel.send("ゲーム環境を準備しました！")
        self.bot.loop.create_task(self.run_game_loop())

async def setup(bot):
    await bot.add_cog(GameCog(bot))
