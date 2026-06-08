import discord, asyncio, time
from config import get_game
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # 相対インポートにすることで、同じフォルダ内のGameCogをエディタが解決しやすくなります
    from .game import GameCog

class DiscussionView(discord.ui.View):
    def __init__(self, timeout):
        super().__init__(timeout=timeout)
        self.ready_players = set()
        self.extend_players = set()
        self.skip_event = asyncio.Event()
        self.extend_event = asyncio.Event()
        self.remaining_time = timeout
        self.extended = False

    @discord.ui.button(label="➕ 時間延長 (0/0)", style=discord.ButtonStyle.primary)
    async def extend(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        game = get_game(interaction.guild.id)
        if not isinstance(user, discord.Member) or user not in game.alive_players:
            return await interaction.response.send_message("生存者のみ可能です。", ephemeral=True)
        
        if self.extended:
            return await interaction.response.send_message("⚠️ 延長は1回までです。", ephemeral=True)

        self.extend_players.add(user.id)
        alive_count = len(game.alive_players)
        needed = (alive_count // 2) + 1
        
        button.label = f"時間延長 ({len(self.extend_players)}/{needed})"
        
        if len(self.extend_players) >= needed:
            self.extended = True
            button.disabled = True
            button.label = "✅ 延長済み"
            self.extend_event.set()
            await interaction.response.edit_message(content="⏳ 過半数の賛成により、議論時間を **60秒** 延長しました！", view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="投票に進む (0/0)", style=discord.ButtonStyle.secondary)
    async def ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        # guildの存在を確認することで、userがMemberであることをエディタに確信させます
        guild = interaction.guild
        user = interaction.user
        game = get_game(interaction.guild.id)
        
        if not guild or not isinstance(user, discord.Member) or user not in game.alive_players:
            return await interaction.response.send_message("生存者のみ可能です。", ephemeral=True)
        
        user_id = user.id
        self.ready_players.add(user_id)
        alive_count = len(game.alive_players)
        needed = (alive_count // 2) + 1
        
        button.label = f"投票に進む ({len(self.ready_players)}/{needed})"
        
        if len(self.ready_players) >= needed:
            button.style = discord.ButtonStyle.success
            button.disabled = True
            self.skip_event.set()
            await interaction.response.edit_message(content=f"✅ {len(self.ready_players)}名が賛成したため、投票に移行します。", view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        self.skip_event.set()

async def start_discussion(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    昼の議論フェーズを開始する
    
    Args:
        channel: メインチャンネル
    """
    game = get_game(channel.guild.id)
    # 【アイテム効果】「沈黙の御札」を貼られている人はミュートを解除しない
    alive_listeners = []
    for p in game.alive_players:
        if isinstance(p, discord.Member):
            if p.id in game.silenced_players:
                # VCミュート設定
                try:
                    await p.edit(mute=True) # VCミュート維持
                except: pass
                # テキストチャンネルの送信権限を剥奪
                await channel.set_permissions(p, send_messages=False)
                await channel.send(f"🤐 **{p.display_name} さんは「沈黙の御札」の呪いにより、今日の議論での発言・チャット（VC/テキスト両方）が禁止されています！**")
            else:
                alive_listeners.append(p)
            
    # 呪いにかかっていない生存者のミュートを解除
    for p in alive_listeners:
        if isinstance(p, discord.Member):
            try:
                await p.edit(mute=False)
                # テキストチャンネルの送信権限を戻す
                await channel.set_permissions(p, overwrite=None)
            except Exception as e:
                print(f"⚠️ ミュート解除失敗 ({p.display_name}): {e}")

    # 終了時刻を計算してDiscordの相対タイムスタンプを作成
    end_timestamp = int(time.time() + game.discussion_time)
    
    await channel.send(f"💬 昼の議論を開始します。議論終了まで： <t:{end_timestamp}:R>\n生存者の皆さんは話し合ってください！")
    if game.log_channel:
        await game.log_channel.send("💬 昼の議論フェーズに入りました。")
    game.save_to_file(channel.guild.id)
    
    # スキップボタンの表示
    view = DiscussionView(timeout=float(game.discussion_time))
    alive_count = len(game.alive_players)
    needed = (alive_count // 2) + 1
    
    # 最初のボタンを取得してラベルを更新
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            if "投票に進む" in str(item.label):
                item.label = f"投票に進む (0/{needed})"
            elif "時間延長" in str(item.label):
                item.label = f"時間延長 (0/{needed})"

    await channel.send("💡 議論を切り上げて投票に進むには、下のボタンを押してください（過半数の賛成が必要）。", view=view)
    
    # 議論終了の待機ループ
    while True:
        try:
            # スキップボタンまたはタイムアウトを待つ
            await asyncio.wait_for(view.skip_event.wait(), timeout=view.remaining_time)
            break
        except asyncio.TimeoutError:
            # タイムアウト時に延長イベントがセットされていたら、時間を足してループを継続
            if view.extended and view.extend_event.is_set():
                view.remaining_time = 60.0
                view.extend_event.clear()
                continue
            break

    await channels.mute_all_alive_players(mute_status=True)
    # 昼フェーズ後に沈黙の呪いをクリア（翌昼には効果がなくなる）
    game.silenced_players.clear()
    # 狂人の混乱効果もクリア
    game.confused_players.clear() 

    await channel.send("⏱️ 議論時間が終了しました。これより投票（処刑対象の選出）に移ります。")
    await self.start_voting(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
