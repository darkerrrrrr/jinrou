import discord, random, io
from config import get_game, RoleName, update_leaderboard
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cogs.game import GameCog

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
from cogs.item import reset_items

async def setup(bot):
    pass # GameCogは cogs/game.py で登録されるため、ここでは何もしない


async def execute_game_start(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    ゲーム開始時の役職配置と初期化を行う
    
    Args:
        channel: メインチャンネル
    """
    game = get_game(channel.guild.id)
    role_map = {
        RoleName.WOLF: Werewolf, 
        RoleName.SEER: Seer, 
        RoleName.MEDIUM: Medium, 
        RoleName.HUNTER: Hunter, 
        RoleName.THIEF: Thief, 
        RoleName.MADMAN: Madman, 
        RoleName.SK: SerialKiller, 
        RoleName.VILLAGER: Villager
    }
    
    # 設定された役職をリスト化
    deck = [role_map[n]() for n, c in game.role_settings.items() for _ in range(c)]
    
    # 参加人数に合わせて調整
    if len(deck) > len(game.players):
        # 設定枚数が多い場合はランダムに削る
        random.shuffle(deck)
        deck = deck[:len(game.players)]
    elif len(deck) < len(game.players): 
        # 足りない分を村人で埋める
        for _ in range(len(game.players) - len(deck)):
            deck.append(Villager())
    
    random.shuffle(deck)
    
    game.roles = {p: deck[i] for i, p in enumerate(game.players)}
    for p, role in game.roles.items(): 
        role.player = p
    
    # 全プレイヤーに役職を通知
    werewolves = [p for p, r in game.roles.items() if r.name == RoleName.WOLF]
    for p, role in game.roles.items():
        try:
            msg = f"🔮 あなたの役職は 【**{role.name}**】 (陣営: {role.team}) です。"
            # 人狼同士の確認
            if role.name == RoleName.WOLF and len(werewolves) > 1:
                partners = [w.display_name for w in werewolves if w != p]
                msg += f"\n🐺 仲間の人狼: {', '.join(partners)}"
            await p.send(msg)
        except Exception as e:
            err_msg = f"⚠️ {p.mention} への役職通知DM送信に失敗しました。設定を確認してください。"
            print(f"❌ {err_msg}: {e}")
            if game.log_channel:
                await game.log_channel.send(err_msg)
    
    # ゲームチャンネルを生成
    await channels.create_game_channels(channel.guild)
    await channels.setup_wolf_permissions(channel.guild)
    
    game.is_playing = True
    game.alive_players = game.players.copy()
    game.thief_action_done = False
    
    # アイテム(拡声器など)が発動したときに全体通知を送るチャンネルを記憶
    game.text_channel = channel 
    game.silenced_players.clear() # ミュートプレイヤーリストの初期化
    game.confused_players.clear() # 混乱プレイヤーリストの初期化
    
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
    
    await game.save_state(channel.guild)
    await self.start_night(channel)


async def check_game_over(self: 'GameCog', channel: discord.TextChannel) -> bool:
    """
    勝利条件をチェックし、ゲーム終了処理を行う
    
    Args:
        channel: メインチャンネル
        
    Returns:
        ゲームが終了した場合はTrue、続行する場合はFalse
    """
    game = get_game(channel.guild.id)
    victory_message = game.check_victory()
    if victory_message:
        game.is_playing = False
        await channels.mute_all_alive_players(channel.guild, mute_status=False)

        # 🏆 ランキングの更新
        winner_team = ""
        if "人狼陣営" in victory_message: winner_team = "人狼"
        elif "村人陣営" in victory_message: winner_team = "村人"
        elif "シリアルキラー" in victory_message: winner_team = "シリアルキラー"

        if winner_team:
            # 勝利陣営に属する全プレイヤー（死亡者含む）のIDを抽出
            winners = [
                p.id for p, role in game.roles.items() 
                if getattr(role, "team", "") == winner_team
            ]
            if winners:
                # 1. 統計の更新（参加者全員を対象に生存率なども計算）
                update_leaderboard(
                    channel.guild.id, 
                    winners, 
                    [p.id for p in game.players], 
                    [p.id for p in game.alive_players],
                    winner_team
                )

                # 2. 勝利ロールの付与
                try:
                    role_name = "🐺人狼勝利者"
                    role = discord.utils.get(channel.guild.roles, name=role_name)
                    if not role:
                        role = await channel.guild.create_role(name=role_name, color=discord.Color.gold(), reason="人狼ゲーム勝利者用")
                    
                    for winner_id in winners:
                        member = channel.guild.get_member(winner_id)
                        if member:
                            await member.add_roles(role)
                except Exception as e:
                    print(f"⚠️ ロール付与失敗: {e}")
        
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
        
        # タイムラインの追加 (1024文字制限を考慮して分割)
        if game.event_log:
            log_text = "\n".join(game.event_log)
            # 1000文字ごとに区切ってフィールドを追加
            chunks = [log_text[i:i+1000] for i in range(0, len(log_text), 1000)]
            for i, chunk in enumerate(chunks):
                field_name = "📜 ゲームの記録（タイムライン）" if i == 0 else f"📜 タイムライン (続き {i+1})"
                embed.add_field(
                    name=field_name,
                    value=chunk,
                    inline=False
                )

        # 📜 詳細ログをテキストファイルとして作成して送信
        full_log = "\n".join(game.event_log)
        file = discord.File(io.StringIO(full_log), filename=f"game_log_{channel.guild.id}.txt")

        await channel.send(embed=embed, file=file)
        await game.log_channel.send(f"🏁 ゲームが終了しました。結果: {victory_message}")
        await game.log_channel.send("─── ゲームログの記録を終了しました ───")
        return True
    return False
