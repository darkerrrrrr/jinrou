import discord, random, io, asyncio, os
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
            
            # ゲーム開始DMを送信
            try:
                await p.send("🎮 **人狼ゲームが開始されました！**\nあなたの役職DMをご確認ください。")
            except Exception as e:
                print(f"⚠️ {p.display_name} へのゲーム開始DM送信失敗: {e}")

            # 役職DMを送信
            # 人狼同士の確認
            if role.name == RoleName.WOLF and len(werewolves) > 1:
                partners = [w.display_name for w in werewolves if w != p]
                msg += f"\n🐺 仲間の人狼: {', '.join(partners)}"
            dm_msg = await p.send(msg)
            game.role_dm_messages[p.id] = dm_msg.id # DMメッセージIDを保存
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
    
    start_embed = discord.Embed(title="🎮 人狼ゲーム開始！", color=discord.Color.gold())
    start_embed.description = (
        "🚀 **ゲームが始まりました！**\n\n"
        "各プレイヤーのDMに役職が通知されました。ご確認ください。\n\n"
        f"【専用チャンネル】\n"
        f"🐺 人狼用: {game.wolf_channel.mention}\n"
        f"📜 ログ用: {game.log_channel.mention}\n\n"
        "【ボイスチャンネル】\n"
        f"🔊 生存者: {game.alive_vc.mention}\n"
        f"👻 墓場: {game.dead_vc.mention}\n"
    )
    start_embed.set_footer(text="※プレイヤーは生存者ボイスチャンネルに移動してください。\n夜フェーズに入ると、DMで行動を促されます。")
    
    await channel.send(embed=start_embed)
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

        # 📢 「📊人狼戦績・結果」チャンネルを探し、なければ自動生成する
        result_destination = discord.utils.get(channel.guild.text_channels, name="📊人狼戦績・結果")
        if not result_destination:
            try:
                # ゲーム用カテゴリの外（サーバーのトップレベル）に作成します
                result_destination = await channel.guild.create_text_channel("📊人狼戦績・結果", reason="人狼ゲームの結果記録用")
                await result_destination.send("📁 **人狼アーカイブ**：ここにゲームの対戦記録が自動的に保存されます。")
            except Exception:
                # 万が一作成に失敗した場合は、ボットを呼び出した元のチャンネルを予備として使用
                result_destination = game.text_channel or channel

        await result_destination.send(embed=embed, file=file)

        await game.log_channel.send(f"🏁 ゲームが終了しました。結果: {victory_message}")
        await game.log_channel.send("─── ゲームログの記録を終了しました ───")

        # --- ゲーム終了後のクリーンアップ ---
        # 1. 募集メッセージのViewを削除
        if game.recruit_message:
            try:
                await game.recruit_message.edit(view=None)
            except Exception as e:
                print(f"⚠️ 募集メッセージのView削除失敗: {e}")

        # 2. 作成したチャンネルとカテゴリを削除
        channels_to_delete = []
        category_to_delete = None

        # いずれかのチャンネルからカテゴリを取得
        if game.progress_channel:
            if game.progress_channel.category:
                category_to_delete = game.progress_channel.category
            channels_to_delete.append(game.progress_channel)
        if game.wolf_channel: channels_to_delete.append(game.wolf_channel)
        if game.log_channel: channels_to_delete.append(game.log_channel)
        if game.dead_channel: channels_to_delete.append(game.dead_channel)
        if game.alive_vc: channels_to_delete.append(game.alive_vc)
        if game.dead_vc: channels_to_delete.append(game.dead_vc)
        if game.data_channel: channels_to_delete.append(game.data_channel)

        # カテゴリがあればカテゴリごと削除（最も効率的）
        if category_to_delete:
            try:
                # カテゴリ内の全チャンネルを削除してからカテゴリを削除
                await asyncio.gather(*[c.delete() for c in category_to_delete.channels])
                await category_to_delete.delete()
                print(f"✅ カテゴリ '{category_to_delete.name}' とその中のチャンネルを削除しました。")
            except Exception as e:
                print(f"⚠️ カテゴリ '{category_to_delete.name}' 削除失敗: {e}。個別のチャンネル削除を試みます。")
                # カテゴリ削除失敗時は個別に削除を試みる
                for ch in channels_to_delete:
                    if ch:
                        try:
                            await ch.delete()
                        except Exception as e_ch:
                            print(f"⚠️ チャンネル '{ch.name}' 削除失敗: {e_ch}")
        else:
            # カテゴリが特定できない場合は個別に削除
            for ch in channels_to_delete:
                if ch:
                    try:
                        await ch.delete()
                    except Exception:
                        pass

        # 3. 保存されていた一時的なゲームデータファイルを削除
        state_file = f"data/game_{channel.guild.id}.json"
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except Exception as e:
                print(f"⚠️ セーブデータ削除失敗: {e}")

        # 4. gameオブジェクトのチャンネル参照をクリア (reset_stateで大部分はクリアされるが念のため)
        game.progress_channel = None
        game.wolf_channel = None
        game.log_channel = None
        game.dead_channel = None
        game.alive_vc = None
        game.dead_vc = None
        game.data_channel = None
        game.recruit_message = None # メッセージ参照もクリア

        # 5. gameオブジェクトの状態をリセット
        # 6. DMで送った役職通知メッセージを削除
        for player_id, msg_id in game.role_dm_messages.items():
            player = channel.guild.get_member(player_id)
            if player:
                try:
                    dm_channel = await player.create_dm()
                    msg = await dm_channel.fetch_message(msg_id)
                    await msg.delete()
                except Exception as e:
                    print(f"⚠️ {player.display_name} の役職通知DM削除失敗: {e}")
        game.reset_state()
        return True
    return False
