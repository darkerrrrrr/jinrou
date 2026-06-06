import discord, random, asyncio, sys, os
from discord.ext import commands

sys.path.append(os.getcwd())

from config import game
from views import RecruitView
from actions import ActionView
import channels

from roles.werewolf import Werewolf
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.serial_killer import SerialKiller
from roles.villager import Villager

class GameCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command()
    async def setup(self, ctx):
        game.host = ctx.author
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(), view=view)

    async def execute_game_start(self, channel):
        role_map = {"人狼": Werewolf, "占い師": Seer, "霊媒師": Medium, "狩人": Hunter, "怪盗": Thief, "狂人": Madman, "シリアルキラー": SerialKiller, "村人": Villager}
        deck = [role_map[n]() for n, c in game.role_settings.items() for _ in range(c)]
        while len(deck) < len(game.players): deck.append(Villager())
        random.shuffle(deck)
        game.roles = {p: deck[i] for i, p in enumerate(game.players)}
        for p, role in game.roles.items(): role.player = p
        
        await channels.create_game_channels(channel.guild)
        await channels.setup_wolf_permissions()
        
        game.is_playing = True
        game.alive_players = game.players.copy()
        
        start_message = (
            f"ゲームを開始しました。\n"
            f"【テキスト】\n"
            f"・人狼用: {game.wolf_channel.mention}\n"
            f"・ログ用: {game.log_channel.mention}\n\n"
            f"【ボイス】\n"
            f"・生存者用: {game.alive_vc.mention}\n"
            f"・墓場用: {game.dead_vc.mention}\n"
            f"※プレイヤーは生存者ボイスチャンネルに移動してください。"
        )
        await channel.send(start_message)
        await game.log_channel.send("─── ゲームログの記録を開始しました ───")
        
        await self.start_night(channel)

    async def start_night(self, channel):
        game.actions = {}
        await channel.send("夜が訪れました。各役職者はDMを確認してください。")
        await game.log_channel.send("🌙 夜フェーズに移行しました。")
        
        for player, role in game.roles.items():
            if player not in game.alive_players: continue
            label = role.get_action_label()
            if label:
                await player.send(f"【{role.name}】です。今夜の{label}先を選んでください。", view=ActionView(player, label))
        await asyncio.sleep(game.night_time)
        await self.process_night_results(channel)

    async def process_night_results(self, channel):
        dead_list = [data['target'] for actor, data in game.actions.items() if data['action'] == "襲撃"]
        await game.log_channel.send("☀️ 朝フェーズになり、夜の結果を処理しています。")
        
        if dead_list:
            for p in dead_list:
                if p in game.alive_players: game.alive_players.remove(p)
                await channels.handle_player_death_vc(p)
            
            result_str = "昨夜の犠牲者: " + ", ".join([p.display_name for p in dead_list])
            await channel.send(result_str)
            await game.log_channel.send(f"❌ 犠牲者: {result_str}")
        else:
            msg = "昨夜は誰も犠牲になりませんでした。"
            await channel.send(msg)
            await game.log_channel.send(f"🛡️ {msg}")
        game.actions = {}

async def setup(bot): await bot.add_cog(GameCog(bot))