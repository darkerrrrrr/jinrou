import discord, random
from config import game
import channels

# 役職インポート
from roles.werewolf import Werewolf
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.serial_killer import SerialKiller
from roles.villager import Villager

# アイテムシステム関連
from cogs.item import silenced_players

async def setup(bot):
    pass


async def execute_game_start(self, channel):
    """ゲーム開始時の役職配置と初期化"""
    role_map = {
        "人狼": Werewolf, 
        "占い師": Seer, 
        "霊媒師": Medium, 
        "狩人": Hunter, 
        "怪盗": Thief, 
        "狂人": Madman, 
        "シリアルキラー": SerialKiller, 
        "村人": Villager
    }
    deck = [role_map[n]() for n, c in game.role_settings.items() for _ in range(c)]
    
    while len(deck) < len(game.players): 
        deck.append(Villager())
    random.shuffle(deck)
    
    game.roles = {p: deck[i] for i, p in enumerate(game.players)}
    for p, role in game.roles.items(): 
        role.player = p
    
    # 全プレイヤーに役職を通知
    for p, role in game.roles.items():
        try:
            await p.send(f"🔮 あなたの役職は 【**{role.name}**】 (陣営: {role.team}) です。")
        except Exception as e:
            print(f"❌ {p.display_name} へのDM送信に失敗: {e}")
    
    # ゲームチャンネルを生成
    await channels.create_game_channels(channel.guild)
    await channels.setup_wolf_permissions()
    
    game.is_playing = True
    game.alive_players = game.players.copy()
    game.thief_action_done = False
    
    # アイテム(拡声器など)が発動したときに全体通知を送るチャンネルを記憶
    game.text_channel = channel 
    silenced_players.clear() # ミュートプレイヤーリストの初期化
    
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


async def check_game_over(self, channel):
    """勝利条件をチェック"""
    victory_message = game.check_victory()
    if victory_message:
        game.is_playing = False
        await channels.mute_all_alive_players(mute_status=False)
        
        # ゲーム終了メッセージ
        embed = discord.Embed(
            title="🏁 ゲーム終了！ 最終結果", 
            color=discord.Color.gold(), 
            description=f"🏆 **{victory_message}**"
        )
        roles_reveal = ""
        for p, role in game.roles.items():
            status = "🟢 生存" if p in game.alive_players else "💀 死亡"
            roles_reveal += f"・{p.mention} : **{role.name}** ({status})\n"
        embed.add_field(name="👥 全員の配役", value=roles_reveal)
        
        await channel.send(embed=embed)
        await game.log_channel.send(f"🏁 ゲームが終了しました。結果: {victory_message}")
        await game.log_channel.send("─── ゲームログの記録を終了しました ───")
        return True
    return False
