import discord
from config import game

async def create_game_channels(guild):
    category = await guild.create_category("🐺人狼ゲーム")
    
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
    game.alive_vc = await guild.create_voice_channel("🔊-生存者村", category=category)
    
    # 3. 霊界・墓場（初期状態は全員ロック。生きてる人はチャンネルの存在すら見えません）
    game.dead_channel = await guild.create_text_channel("👻-墓場・霊界テキスト", category=category, overwrites=overwrites_text)
    game.dead_vc = await guild.create_voice_channel("👻-墓場・霊界", category=category, overwrites=overwrites_vc)
    
    return category

async def setup_wolf_permissions():
    if not game.wolf_channel: return
    for p, role in game.roles.items():
        if role.name == "人狼":
            await game.wolf_channel.set_permissions(p, read_messages=True, send_messages=True, view_channel=True)

async def handle_player_death_vc(player):
    # 【追加ポイント】プレイヤーが死亡した瞬間に、その人だけの「霊界の鍵」を開ける
    if game.dead_channel:
        # 霊界テキストを見えるようにし、発言も許可
        await game.dead_channel.set_permissions(player, read_messages=True, send_messages=True, view_channel=True)
        
    if game.dead_vc:
        # 霊界ボイスチャンネルを見えるようにし、接続（入室）も許可
        await game.dead_vc.set_permissions(player, view_channel=True, connect=True)

    # 既にボイスチャンネルに入っている場合は、霊界ボイスへ強制移動
    if game.dead_vc and player.voice and player.voice.channel:
        try: 
            await player.move_to(game.dead_vc)
        except: 
            pass
