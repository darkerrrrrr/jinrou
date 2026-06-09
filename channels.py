import discord
from config import get_game, RoleName
import asyncio
from typing import Optional

async def create_game_channels(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    """
    ゲーム用のチャンネルカテゴリと各チャンネルを作成する
    
    Args:
        guild: チャンネルを作成するDiscordサーバー
        
    Returns:
        作成したカテゴリチャンネル
    """
    game = get_game(guild.id)
    category_name = f"🐺人狼ゲーム-{guild.id}"
    
    # 既存の同名カテゴリーをクリーンアップ
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel) and channel.name == category_name:
            try:
                # カテゴリ内のチャンネルを並列で削除
                await asyncio.gather(*[c.delete() for c in channel.channels])
                await channel.delete()
            except Exception as e:
                print(f"⚠️ 既存カテゴリー削除失敗: {e}")
    
    # カテゴリー自体をデフォルトで「全員非表示・接続不可」にする
    category_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False)
    }
    category = await guild.create_category(category_name, overwrites=category_overwrites)

    # 公開チャンネル（進行用など）のための権限
    public_view = discord.PermissionOverwrite(view_channel=True)
    public_vc = discord.PermissionOverwrite(view_channel=True, connect=True)
    
    # 参加者全員に対して明示的に「非表示」にするためのベース
    # これにより、他のロールで「表示」が許可されていても、メンバー個別の拒否が優先されます
    private_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False, read_messages=False)
    }
    for p in game.players:
        # 個別のメンバーに対して、表示・メッセージ閲覧・接続をすべて拒否する
        private_overwrites[p] = discord.PermissionOverwrite(view_channel=False, read_messages=False, connect=False)

    # 0. ゲーム進行チャンネル（メインの舞台）
    game.progress_channel = await guild.create_text_channel(
        "📢ゲーム進行", 
        category=category, 
        overwrites={guild.default_role: public_view}
    )

    # 1. 人狼チャット（デフォルトで全員非表示）
    wolf_overwrites = private_overwrites.copy()
    game.wolf_channel = await guild.create_text_channel("🐺人狼チャット", category=category, overwrites=wolf_overwrites)
    
    # 🐺人狼用ナレーションスレッドの作成
    wolf_starter = await game.wolf_channel.send("📢 **人狼ナレーション専用スレッド**\nここでは進行上のアナウンスのみが行われます。")
    game.wolf_thread = await wolf_starter.create_thread(name="🐺人狼用ナレーション")
    # プレイヤーがスレッドに書き込めないように設定
    for p in game.players:
        await game.wolf_thread.set_permissions(p, send_messages=False)
    
    # 2. ゲームログと生存者ボイス（これらは全員が見えたり入れたりしてOK）
    # ゲームログは進行中に秘密が漏れないよう、全員非表示にする
    log_overwrites = private_overwrites.copy()
    if guild.me:
        log_overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    game.log_channel = await guild.create_text_channel("📜ゲームログ", category=category, overwrites=log_overwrites)
    
    # 生存者村ボイスは見れるし入れるようにする
    game.alive_vc = await guild.create_voice_channel(
        "🔊生存者村", 
        category=category, 
        overwrites={guild.default_role: public_vc}
    )
    
    # 3. 霊界・墓場（デフォルトで全員非表示）
    dead_overwrites = private_overwrites.copy()
    game.dead_channel = await guild.create_text_channel("👻墓場・霊界テキスト", category=category, overwrites=dead_overwrites)

    # 👻霊界用ナレーションスレッドの作成
    dead_starter = await game.dead_channel.send("📢 **霊界ナレーション専用スレッド**\nここでは進行上のアナウンスのみが行われます。")
    game.dead_thread = await dead_starter.create_thread(name="👻霊界用ナレーション")
    # プレイヤーがスレッドに書き込めないように設定
    for p in game.players:
        await game.dead_thread.set_permissions(p, send_messages=False)

    game.dead_vc = await guild.create_voice_channel("👻墓場・霊界", category=category, overwrites=dead_overwrites)
    
    # 4. データ保持チャンネル（ボット自身のみが読み書き可能にする）
    data_overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    if guild.me:
        data_overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
    game.data_channel = await guild.create_text_channel("🔐人狼データ保持", category=category, overwrites=data_overwrites)
    
    return category

async def setup_wolf_permissions(guild: discord.Guild) -> None:
    """人狼チャットの権限を設定する（人狼のみアクセス可能）"""
    game = get_game(guild.id)
    if not game.wolf_channel: return
    
    # 現在の人狼リストを特定
    wolves = [p for p, role in game.roles.items() if role.name == RoleName.WOLF]
    
    # 一旦、全員の権限をリセット（または個別に削除）するのではなく、
    # 役職を持っている全員に対して、人狼か否かで権限を上書き設定する
    for p, role in game.roles.items():
        is_wolf = (role.name == RoleName.WOLF)
        try:
            # 人狼なら許可、そうでないなら(怪盗に奪われた場合など)不許可
            await game.wolf_channel.set_permissions(
                p, 
                read_messages=is_wolf, 
                send_messages=is_wolf, 
                view_channel=is_wolf
            )
        except Exception as e:
            print(f"⚠️ 人狼チャット権限更新失敗 ({p.display_name}): {e}")

async def handle_player_death_vc(player: discord.Member, guild: discord.Guild) -> None:
    """
    プレイヤー死亡時のボイスチャンネル権限を設定する
    
    Args:
        player: 死亡したプレイヤー
    """
    game = get_game(guild.id)
    # 【追加ポイント】プレイヤーが死亡した瞬間に、その人だけの「霊界の鍵」を開ける
    if game.dead_channel:
        try:
            # 霊界テキストを見えるようにし、発言も許可
            await game.dead_channel.set_permissions(player, read_messages=True, send_messages=True, view_channel=True)
        except Exception as e:
            print(f"⚠️ 死亡時のテキストチャンネル権限設定失敗 ({player.display_name}): {e}")
        
    if game.dead_vc:
        try:
            # 霊界ボイスチャンネルを見えるようにし、接続（入室）も許可
            await game.dead_vc.set_permissions(player, view_channel=True, connect=True)
        except Exception as e:
            print(f"⚠️ 死亡時のボイスチャンネル権限設定失敗 ({player.display_name}): {e}")

    # 既にボイスチャンネルに入っている場合は、霊界ボイスへ強制移動
    if game.dead_vc and player.voice and player.voice.channel:
        try: 
            await player.move_to(game.dead_vc)
        except Exception as e:
            print(f"⚠️ ボイスチャンネル強制移動失敗 ({player.display_name}): {e}")

# ==========================================
# 👇 ここから新しくミュート制御用関数を追加
# ==========================================

async def mute_all_alive_players(guild: discord.Guild, mute_status: bool) -> None:
    """
    生存者ボイスチャンネルにいる生存プレイヤーを全員一括でマイクミュート制御する
    mute_status: Trueでマイクミュート（喋れない）、Falseで解除
    """
    game = get_game(guild.id)
    if not game.alive_vc: return

    tasks = []
    for member in game.alive_vc.members:
        # 生存者ボイスチャンネルの中にいる、かつ「現在ゲームで生存しているプレイヤー」のみを対象にする
        if member in game.alive_players:
            # マイクミュートのみを制御し、スピーカー（deafen）には干渉しない
            tasks.append(member.edit(mute=mute_status))
    
    if tasks:
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"⚠️ VC一括制御失敗: {e}")
