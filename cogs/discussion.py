import discord, asyncio, time, random
from config import get_game
import channels
from typing import TYPE_CHECKING, Optional, cast
from .item import QuickItemView
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
            new_embed = discord.Embed(
                title="💬 昼の議論開始",
                description=f"議論終了まで： <t:{new_ts}:R>\n生存者の皆さんは話し合ってください！",
                color=discord.Color.light_grey()
            )
            try:
                await self.timer_msg.edit(embed=new_embed)
            except: pass

            self.extend_event.set()
            await game.save_state(guild) # 保存
            ext_confirm_embed = discord.Embed(description="⏳ 過半数の賛成により、議論時間を **60秒** 延長しました！", color=discord.Color.green())
            await interaction.response.edit_message(embed=ext_confirm_embed, view=self)
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
            skip_embed = discord.Embed(description=f"✅ {len(self.ready_players)}名が賛成したため、投票に移行します。", color=discord.Color.green())
            await interaction.response.edit_message(embed=skip_embed, view=self)
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
    target_channel = game.progress_channel or channel
    game.vc_locked = False  # 議論開始なのでロック解除

    # 📦 議論中のランダム・アイテムドロップ・タスク
    async def spawn_quick_item():
        try:
            # 75%の確率で発生するように調整 (0.0〜1.0のうち0.75未満なら実行)
            if random.random() >= 0.75:
                return

            # 議論時間の20%〜80%の間のランダムなタイミングで1回出現
            wait_time = random.uniform(game.discussion_time * 0.2, game.discussion_time * 0.8)
            await asyncio.sleep(wait_time)
            
            if bool(game.is_playing) and target_channel:
                drop_embed = discord.Embed(title="📦 村の広場に荷物が届きました！", description="一番早くボタンを押した生存者がアイテムを獲得できます！", color=discord.Color.gold())
                await target_channel.send(embed=drop_embed, view=QuickItemView(channel.guild.id))
        except asyncio.CancelledError:
            pass # 議論が早く終わった場合はキャンセルされる


    # 【アイテム効果】「沈黙の御札」を貼られている人はミュートを解除しない
    alive_listeners = []
    for p in game.alive_players:
        if isinstance(p, discord.Member):
            if p.id in game.silenced_players:
                # アイテム効果：マイク（発言）を禁止する
                if p.voice:
                    try:
                        await p.edit(mute=True) 
                    except discord.Forbidden: pass
                    except Exception: pass

                # テキストチャンネルの送信権限を剥奪
                await target_channel.set_permissions(p, send_messages=False)
                mute_embed = discord.Embed(description=f"🤐 **{p.mention} さんは「沈黙の御札」の呪いにより、今日の発言が禁止されています。**", color=discord.Color.dark_grey())
                await target_channel.send(embed=mute_embed)
            else:
                alive_listeners.append(p)
            
    # 呪いにかかっていない生存者のミュートを解除
    for p in alive_listeners:
        if isinstance(p, discord.Member):
            if p.voice:
                try:
                    # マイクミュートを解除する
                    await p.edit(mute=False)
                except discord.Forbidden: pass
                except Exception: pass
            
            # テキストチャンネルの送信権限を戻す
            await target_channel.set_permissions(p, overwrite=None)

    # 終了時刻を計算してDiscordの相対タイムスタンプを作成
    end_timestamp = int(time.time() + game.discussion_time)
    
    disc_embed = discord.Embed(
        title="💬 昼の議論開始",
        description=f"議論終了まで： <t:{end_timestamp}:R>\n生存者の皆さんは話し合ってください！",
        color=discord.Color.light_grey()
    )
    timer_msg = await target_channel.send(embed=disc_embed, silent=True)

    # 霊界のスレッドに議論開始を通知
    if game.dead_thread:
        await game.dead_thread.send(embed=discord.Embed(title="💬 昼の議論開始", description="生存者の推理を聞いてみましょう。", color=discord.Color.light_grey()), silent=False)
    
    if game.log_channel:
        await game.log_channel.send(embed=discord.Embed(description="💬 昼の議論フェーズに入りました。", color=discord.Color.light_grey()))
    await game.save_state(channel.guild)
    
    qte_task = asyncio.create_task(spawn_quick_item())
    
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

    control_embed = discord.Embed(description="💡 議論を切り上げて投票に進むには、下のボタンを押してください（過半数の賛成が必要）。", color=discord.Color.blue())
    disc_control_msg = await target_channel.send(embed=control_embed, view=view, silent=True)
    
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

    qte_task.cancel() # 議論終了時にタスクを停止
    # ⏱️ 議論が終わったので、操作ボタンを消して「あとから推せない」ようにする
    try:
        await disc_control_msg.edit(view=None)
    except: pass

    await channels.mute_all_alive_players(channel.guild, mute_status=True)
    game.vc_locked = True  # 投票フェーズに入るので再びロック
    # 昼フェーズ後に沈黙の呪いをクリア（翌昼には効果がなくなる）
    game.silenced_players.clear()
    # 狂人の混乱効果もクリア
    game.confused_players.clear() 

    await target_channel.send(embed=discord.Embed(description="⏱️ 議論時間が終了しました。これより投票に移ります。", color=discord.Color.orange()), silent=True)
    await self.start_voting(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
