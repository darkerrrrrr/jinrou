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

    # ⚠️ 参加人数が少なすぎると勝利条件が即座に満たされて終了してしまうため制限
    MIN_PLAYERS = 4
    if len(game.players) < MIN_PLAYERS:
        return await channel.send(embed=discord.Embed(
            description=f"❌ 参加人数が足りません。最低 **{MIN_PLAYERS}人** 以上必要です。（現在: {len(game.players)}人）",
            color=discord.Color.red()
        ))

    # 🚀 重複起動を完全に防止
    if game.is_playing:
        return

    # 🚀 ゲーム開始を宣言し、募集メッセージのボタンを「即座に」消す
    game.is_playing = True
    if game.recruit_message:
        try:
            await game.recruit_message.edit(view=None)
        except: pass

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
            role_reveal_embed = discord.Embed(title="🔮 あなたの役職通知", color=discord.Color.purple())
            role_reveal_embed.description = f"あなたの役職は 【**{role.name}**】 です。\n(陣営: {role.team})"
            is_wolf = (role.name == RoleName.WOLF)
            
            # ゲーム開始DMを送信
            try:
                start_embed = discord.Embed(title="🎮 人狼ゲーム開始！", description="あなたの役職DMをご確認ください。", color=discord.Color.gold())
                start_dm = await p.send(embed=start_embed, silent=True)
                game.add_dm_message(p.id, start_dm.id)
            except Exception as e:
                print(f"⚠️ {p.display_name} へのゲーム開始DM送信失敗: {e}")

            # 役職DMを送信
            # 人狼同士の確認
            if role.name == RoleName.WOLF and len(werewolves) > 1:
                partners = [w.display_name for w in werewolves if w != p]
                role_reveal_embed.add_field(name="🐺 仲間の人狼", value=", ".join(partners), inline=False)
            dm_msg = await p.send(embed=role_reveal_embed, silent=not is_wolf)
            game.add_dm_message(p.id, dm_msg.id)
        except Exception as e:
            err_msg = f"⚠️ {p.display_name} への役職通知DM送信に失敗しました。設定を確認してください。"
            print(f"❌ {err_msg}: {e}")
            if game.log_channel:
                await game.log_channel.send(err_msg)
    
    # ゲームチャンネルを生成
    await channels.create_game_channels(channel.guild)
    await channels.setup_wolf_permissions(channel.guild)

    # ⚠️ チャンネル作成に失敗した場合は、エラーを表示して停止させる
    if not game.progress_channel:
        game.is_playing = False
        return await channel.send(embed=discord.Embed(
            description="❌ ゲームチャンネルの作成に失敗しました。Botに「チャンネルの管理」権限があるか確認してください。",
            color=discord.Color.red()
        ))

    target_channel = game.progress_channel
    game.alive_players = game.players.copy()
    game.thief_action_done = False
    
    # アイテム(拡声器など)が発動したときに全体通知を送るチャンネルを記憶
    game.text_channel = target_channel
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
    
    # 元のチャンネルには「開始しました」という合図と、新チャンネルへのリンクのみ送る
    start_notice = discord.Embed(description=f"🚀 ゲームを開始しました！\n進行は {target_channel.mention} で行います。", color=discord.Color.green())
    await channel.send(embed=start_notice, silent=True)
    await target_channel.send(embed=start_embed, silent=True)
    await game.log_channel.send(embed=discord.Embed(description="📊 **ゲームログの記録を開始しました**", color=discord.Color.blue()), silent=True)

    # 🔊 ボイスチャンネル移動の案内は「新チャンネル」に送る
    wait_embed = discord.Embed(
        title="🔊 ボイスチャンネル移動",
        description="⏳ 20秒後にゲームを開始します。未入室の方は **🔊生存者村** へ入ってください。",
        color=discord.Color.blue()
    )
    await target_channel.send(embed=wait_embed, silent=True)

    # 他のボイスチャンネルにいるプレイヤーを「🔊生存者村」へ強制移動させる
    vc_missing = []
    for p in game.players:
        if p.voice and p.voice.channel and p.voice.channel != game.alive_vc:
            try:
                await p.move_to(game.alive_vc)
            except Exception:
                pass # 権限不足などで移動できない場合は無視して手動移動を促す
        elif not p.voice:
            vc_missing.append(p.display_name)

    if vc_missing:
        # 必要であれば、ここで「全員揃っていないので開始できません」とエラーを出して止めることも可能です
        pass

    await asyncio.sleep(20)
    
    # ☀️ 0日目の朝：ゲームの幕開けを宣言
    opening_embed = discord.Embed(
        title="☀️ 0日目：朝",
        description="村に朝が来ました。現在、生存者は全員無事です。\n\nまもなく夜が訪れます。役職者の方は夜の行動に備えてください。",
        color=discord.Color.orange()
    )
    await target_channel.send(embed=opening_embed, silent=True)
    await asyncio.sleep(5) # 状況を確認する短い猶予

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
        game.vc_locked = False

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
                    for p, role_obj in game.roles.items():
                        if getattr(role_obj, "team", "") == winner_team:
                            # 要望通り「人狼ゲーム勝利者(役職名)」という形式で動的にロールを作成・付与
                            role_name = f"人狼ゲーム勝利者({role_obj.name})"
                            
                            role = discord.utils.get(channel.guild.roles, name=role_name)
                            if not role:
                                role = await channel.guild.create_role(
                                    name=role_name, 
                                    color=discord.Color.gold(), 
                                    reason=f"人狼ゲーム勝利者({role_obj.name})用"
                                )
                            await p.add_roles(role)
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
            roles_reveal += f"・{p.display_name} : **{role.name}** ({status})\n"
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

        await result_destination.send(embed=embed, file=file, silent=True)

        await game.log_channel.send(embed=discord.Embed(description=f"🏁 **ゲームが終了しました。結果: {victory_message}**", color=discord.Color.gold()), silent=True)
        await game.log_channel.send(embed=discord.Embed(description="📊 **ゲームログの記録を終了しました**", color=discord.Color.blue()), silent=True)

        # 全てのアナウンスが終わった後にリソースを削除
        await _cleanup_resources(game, channel.guild)

        game.reset_state()
        return True

async def force_stop_game(self: 'GameCog', channel: discord.TextChannel) -> bool:
    """
    ゲームを強制終了し、全リソースをクリーンアップする
    """
    game = get_game(channel.guild.id)
    game.is_playing = False
    game.vc_locked = False
    await _cleanup_resources(game, channel.guild)
    game.reset_state()
    return True

async def _cleanup_resources(game, guild: discord.Guild):
    """全リソースをクリーンアップする内部ヘルパー"""
    # 1. VC移動とミュート解除
    game_category_id = game.progress_channel.category_id if game.progress_channel else None
    target_vc = next((vc for vc in guild.voice_channels if vc.category_id != game_category_id), None)
    
    # 参加者全員を対象にミュート解除を行う（別のVCに移動している可能性も考慮）
    for p in game.players:
        if p.voice: # VCに接続している場合のみ操作可能
            try:
                # ゲーム用VC内にいる場合は、既存のVC（雑談等）へ移動させる
                is_in_game_vc = p.voice.channel and p.voice.channel.category_id == game_category_id
                if is_in_game_vc and target_vc:
                    await p.edit(mute=False, move_to=target_vc)
                else:
                    await p.edit(mute=False)
            except discord.Forbidden:
                print(f"❌ 権限不足: {p.display_name} のミュート解除に失敗しました。")
            except Exception: pass

    # 2. チャンネルとカテゴリの削除
    category = game.progress_channel.category if game.progress_channel else None
    if category:
        try:
            await asyncio.gather(*[c.delete() for c in category.channels])
            await category.delete()
        except: pass

    # 3. 募集メッセージのボタン削除
    if game.recruit_message:
        try: await game.recruit_message.edit(view=None)
        except: pass

    # 4. DM削除
    async def _del_dm(p, mids):
        try:
            ch = await p.create_dm()
            for mid in mids:
                try:
                    msg = await ch.fetch_message(mid)
                    await msg.delete()
                except: pass
        except: pass

    tasks = []
    for pid, mids in game.role_dm_messages.items():
        p = guild.get_member(pid)
        if p: tasks.append(_del_dm(p, mids))
    if tasks: await asyncio.gather(*tasks)

    # 5. セーブデータ削除
    try:
        path = f"data/game_{guild.id}.json"
        if os.path.exists(path): os.remove(path)
    except: pass
