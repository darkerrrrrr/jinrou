import discord, random, asyncio
from discord.ext import commands
from config import game
from views import RecruitView
from roles.wolf import Werewolf
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
        game.host = ctx.author  # 主催者を保存
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(), view=view)

    # 外部からの開始コマンド（念のため残しつつ、中身を共通化）
    @commands.command()
    async def start_game(self, ctx):
        if ctx.author != game.host:
            return await ctx.send("主催者のみが開始できます。")
        if len(game.players) < 3:
            return await ctx.send("3人以上で開始してください。")
        await self.execute_game_start(ctx)

    # 共通のゲーム開始処理
    async def execute_game_start(self, interaction_or_ctx):
        # 役職割り当てロジック
        role_map = {"人狼": Werewolf, "占い師": Seer, "霊媒師": Medium, "狩人": Hunter, "怪盗": Thief, "狂人": Madman, "シリアルキラー": SerialKiller, "村人": Villager}
        deck = [role_map[n](None) for n, c in game.role_settings.items() for _ in range(c)]
        while len(deck) < len(game.players): deck.append(Villager(None))
        random.shuffle(deck)
        game.roles = {p: deck[i] for i, p in enumerate(game.players)}
        for p, role in game.roles.items(): role.player = p
        game.is_playing = True
        game.alive_players = game.players.copy()
        
        await interaction_or_ctx.send("ゲームを開始しました。")

    async def run_game_loop(self):
        while game.is_playing:
            await asyncio.sleep(1)

async def setup(bot): await bot.add_cog(GameCog(bot))
