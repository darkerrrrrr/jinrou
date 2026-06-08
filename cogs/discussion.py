import discord, asyncio, time
from config import get_game
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # 相対インポートにすることで、同じフォルダ内のGameCogをエディタが解決しやすくなります
    from .game import GameCog

class DiscussionView(discord.ui.View):
    def __init__(self, timeout, timer_msg: discord.Message, end_timestamp: int):
        super().__init__(timeout=timeout)
        self.ready_players = set()
        self.extend_players = set()
        self.skip_event = asyncio.Event()
        self.extend_event = asyncio.Event()
        self.timer_msg = timer_msg
        self.end_timestamp = end_timestamp
        self.extended = False

    @discord.ui.button(label="➕ 時間延長 (0/0)", style=discord.ButtonStyle.primary)
    async def extend(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member): return
        game = get_game(guild.id)
        if user not in game.alive_players:
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
            
            # 実際の延長処理：終了時刻を60秒加算し、表示を更新
            self.end_timestamp += 60
            if self.timeout is not None:
                self.timeout += 60
            
            new_ts = int(self.end_timestamp)
            try:
                await self.timer_msg.edit(content=f"💬 昼の議論を開始します。議論終了まで： <t:{new_ts}:R>\n生存者の皆さんは話し合ってください！")
            except: pass

            self.extend_event.set()
            await game.save_state(guild) # 保存
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
            await game.save_state(interaction.guild) # 保存
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
    
    timer_msg = await channel.send(f"💬 昼の議論を開始します。議論終了まで： <t:{end_timestamp}:R>\n生存者の皆さんは話し合ってください！")
    
    if game.log_channel:
        await game.log_channel.send("💬 昼の議論フェーズに入りました。")
    await game.save_state(channel.guild)
    
    # スキップボタンの表示
    view = DiscussionView(timeout=float(game.discussion_time), timer_msg=timer_msg, end_timestamp=end_timestamp)
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
        remaining = view.end_timestamp - time.time()
        if remaining <= 0:
            break

        # スキップまたは延長イベントを待機
        skip_task = asyncio.create_task(view.skip_event.wait())
        extend_task = asyncio.create_task(view.extend_event.wait())

        done, pending = await asyncio.wait(
            [skip_task, extend_task],
            timeout=remaining,
            return_when=asyncio.FIRST_COMPLETED
        )

        for t in pending:
            t.cancel()

        if view.skip_event.is_set():
            break
        if view.extend_event.is_set():
            view.extend_event.clear()
            continue # 延長された終了時刻でループを再開
        if not done: # タイムアウト
            break

    await channels.mute_all_alive_players(channel.guild, mute_status=True)
    # 昼フェーズ後に沈黙の呪いをクリア（翌昼には効果がなくなる）
    game.silenced_players.clear()
    # 狂人の混乱効果もクリア
    game.confused_players.clear() 

    await channel.send("⏱️ 議論時間が終了しました。これより投票（処刑対象の選出）に移ります。")
    await self.start_voting(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
