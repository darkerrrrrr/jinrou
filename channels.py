import discord
from config import game
from typing import Optional

async def create_game_channels(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    """
    ゲーム用のチャンネルカテゴリと各チャンネルを作成する
    
    Args:
        guild: チャンネルを作成するDiscordサーバー
        
    Returns:
        作成したカテゴリチャンネル
    """
    # 既に同名カテゴリーが存在する場合は削除（サーバーIDを含めて安全に）
    category_name = f"🐺人狼ゲーム-{guild.id}"
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel) and channel.name == category_name:
            try:
                await channel.delete()
            except Exception as e:
                print(f"⚠️ 既存カテゴリー削除失敗: {e}")
    
    category = await guild.create_category(category_name)
    
    # サーバーの全員（@everyone）の初期権限設定
    # テキスト用：見るのも読むのも禁止
    text_lock = discord.PermissionOverwrite(read_messages=False, view_channel=False)
    # ボイス用：見るのも入るのも禁止
    vc_lock = discord.PermissionOverwrite(view_channel=False, connect=False)
    
    # 全員一律でロックをかける（@everyoneに対して適用）
    overwrites_text = {guild.default_role: text_lock}
    overwrites_vc = {guild.default_role: vc_lock}
    
    # 1. 人狼チャット（初期状態は全員ロック、あとから人狼だけ許可）
    game.wolf_channel = await guild.create_text_channel("人狼チャット", category=category, overwrites=overwrites_text)
    
    # 2. ゲームログと生存者ボイス（これらは全員が見えたり入れたりしてOK）
    game.log_channel = await guild.create_text_channel("ゲームログ", category=category)
    game.alive_vc = await guild.create_voice_channel("生存者村", category=category)
    
    # 3. 霊界・墓場（初期状態は全員ロック。生きてる人はチャンネルの存在すら見えません）
    game.dead_channel = await guild.create_text_channel("墓場・霊界テキスト", category=category, overwrites=overwrites_text)
    game.dead_vc = await guild.create_voice_channel("墓場・霊界", category=category, overwrites=overwrites_vc)
    
    return category

async def setup_wolf_permissions() -> None:
    """人狼チャットの権限を設定する（人狼のみアクセス可能）"""
    if not game.wolf_channel: return
    for p, role in game.roles.items():
        # 人狼のみ人狼チャットにアクセス可能（狂人は除外）
        if role.name == "人狼":
            try:
                await game.wolf_channel.set_permissions(p, read_messages=True, send_messages=True, view_channel=True)
            except Exception as e:
                print(f"⚠️ 人狼チャット権限設定失敗 ({p.display_name}): {e}")

async def handle_player_death_vc(player: discord.Member) -> None:
    """
    プレイヤー死亡時のボイスチャンネル権限を設定する
    
    Args:
        player: 死亡したプレイヤー
    """
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

async def mute_all_alive_players(mute_status: bool) -> None:
    """
    生存者ボイスチャンネルにいる生存プレイヤーを全員一括でミュート/解除する
    mute_status = True でマイクミュート、False でミュート解除
    """
    if not game.alive_vc: return
    for member in game.alive_vc.members:
        # 生存者ボイスチャンネルの中にいる、かつ「現在ゲームで生存しているプレイヤー」のみを対象にする
        if member in game.alive_players:
            try:
                await member.edit(mute=mute_status)
            except Exception as e:
                print(f"⚠️ ミュート制御失敗 ({member.display_name}): {e}")
