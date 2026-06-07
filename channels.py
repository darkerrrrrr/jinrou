import discord
from config import game

async def create_game_channels(guild):
    category = await guild.create_category("🐺人狼ゲーム")
    
    # 修正ポイント：一般プレイヤーの「閲覧権限（view_channel）」も完全にオフにする
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False)}
    
    # 人狼チャットは誰も見られないロック状態で作成
    game.wolf_channel = await guild.create_text_channel("人狼チャット", category=category, overwrites=overwrites)
    game.log_channel = await guild.create_text_channel("ゲームログ", category=category)
    game.alive_vc = await guild.create_voice_channel("🔊-生存者村", category=category)
    game.dead_vc = await guild.create_voice_channel("👻-墓場・霊界", category=category)
    return category

async def setup_wolf_permissions():
    if not game.wolf_channel: return
    for p, role in game.roles.items():
        if role.name == "人狼":
            # 修正ポイント：見る権限(view_channel)もあわせて人狼だけに付与
            await game.wolf_channel.set_permissions(p, read_messages=True, send_messages=True, view_channel=True)

async def handle_player_death_vc(player):
    if game.dead_vc and player.voice and player.voice.channel:
        try: await player.move_to(game.dead_vc)
        except: pass
