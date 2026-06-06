import discord, random, asyncio
from discord.ext import commands
from config import game
from views import RecruitView
from actions import ActionView
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
        game.is_playing = True
        game.alive_players = game.players.copy()
        await channel.send("ゲームを開始しました。")
        await self.start_night(channel)

    async def start_night(self, channel):
        game.actions = {}
        await channel.send("夜が訪れました。各役職者はDMを確認してください。")
        for player, role in game.roles.items():
            if player not in game.alive_players: continue
            label = role.get_action_label()
            if label:
                await player.send(f"【{role.name}】です。今夜の{label}先を選んでください。", view=ActionView(player, label))
        await asyncio.sleep(game.night_time)
        await self.process_night_results(channel)

    async def process_night_results(self, channel):
        # 簡易的な集計ロジック
        dead_list = [data['target'] for actor, data in game.actions.items() if data['action'] == "襲撃"]
        if dead_list:
            for p in dead_list:
                if p in game.alive_players: game.alive_players.remove(p)
            await channel.send("昨夜の犠牲者: " + ", ".join([p.display_name for p in dead_list]))
        else:
            await channel.send("昨夜は誰も犠牲になりませんでした。")
        game.actions = {}

async def setup(bot): await bot.add_cog(GameCog(bot))
