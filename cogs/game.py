import discord, random, asyncio
from discord.ext import commands
from config import game
from views import RecruitView # 募集用Viewをインポート
from roles.wolf import Werewolf
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

    # 募集パネルを出すためのコマンド
    @commands.command()
    async def setup(self, ctx):
        view = RecruitView()
        await ctx.send(embed=view.create_recruit_embed(), view=view)

    @commands.command()
    async def start_game(self, ctx):
        if len(game.players) < 3: 
            return await ctx.send("3人以上で開始してください。")
        
        # 役職マップ定義
        role_map = {
            "人狼": Werewolf, "占い師": Seer, "霊媒師": Medium,
            "狩人": Hunter, "怪盗": Thief, "狂人": Madman,
            "シリアルキラー": SerialKiller, "村人": Villager
        }
        
        # 役職デッキ作成
        deck = [role_map[n](None) for n, c in game.role_settings.items() for _ in range(c)]
        while len(deck) < len(game.players): 
            deck.append(Villager(None))
        random.shuffle(deck)
        
        # 役職割り当て
        game.roles = {p: deck[i] for i, p in enumerate(game.players)}
        for p, role in game.roles.items(): 
            role.player = p
            
        game.is_playing = True
        game.alive_players = game.players.copy()
        await ctx.send("ゲームを開始しました。")
        
        # ゲームループを開始
        self.bot.loop.create_task(self.run_game_loop())

    async def run_game_loop(self):
        while game.is_playing:
            # ここに自動進行のロジックを追加していきます
            await asyncio.sleep(1)

async def setup(bot):
    await bot.add_cog(GameCog(bot))
