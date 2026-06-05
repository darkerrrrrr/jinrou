import discord
from discord.ext import commands
import asyncio
import random
from collections import Counter
from config import game
from views import RecruitView
from discord.ui import View, Select

# 各役職ファイルのインポート
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
        if hasattr(game, 'game_category'):
            for channel in game.game_category.channels: await channel.delete()
            await game.game_category.delete()
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
            if member.voice and member.voice.channel and hasattr(game, 'game_category'):
                reikai_vc = next((vc for vc in game.game_category.voice_channels if "霊界" in vc.name), None)
                if reikai_vc: await member.edit(mute=False, voice_channel=reikai_vc)
            if game.dead_channel:
                await game.dead_channel.set_permissions(member, read_messages=True, send_messages=True)
                await game.dead_channel.send(f"👻 {member.mention} さんが霊界へ移動しました。")
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
            # [朝フェーズ・投票・夜のロジックはあなたの元コードから引き継いでいます]
            # ※勝利判定の後に以下の自動掃除を実行します
            winner = game.check_victory()
            if winner:
                await self.mute_all_alive(False, "終了")
                await game.log_channel.send(f"🏁 ゲーム終了: {winner}\n5秒後にチャンネルを整理します！")
                await asyncio.sleep(5)
                await self.cleanup_game_environment()
                game.is_playing = False
                break
            day_count += 1
            await asyncio.sleep(1)

    @commands.command()
    async def start_game(self, ctx):
        if len(game.players) < 3: return await ctx.send("3人以上で開始してください。")

        # 1. チャンネル環境構築（自動）
        guild = ctx.guild
        category = await guild.create_category("🐺 人狼ゲーム")
        game.game_category = category
        game.log_channel = await guild.create_text_channel("進行ログ", category=category)
        await guild.create_voice_channel("議論用ボイス", category=category)
        await guild.create_voice_channel("霊界ボイス", category=category)
        game.dead_channel = await guild.create_text_channel(
            "霊界チャット", category=category, 
            overwrites={guild.default_role: discord.PermissionOverwrite(read_messages=False)}
        )

        # 2. 役職割り当て
        game.is_playing = True
        game.alive_players = game.players.copy()
        # [あなたの役職配布ロジックをここに記載]
        
        await game.log_channel.send("ゲーム環境を準備しました！")
        self.bot.loop.create_task(self.run_game_loop())

async def setup(bot):
    await bot.add_cog(GameCog(bot))
