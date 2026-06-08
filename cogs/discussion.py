import discord, asyncio
from config import game
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # 相対インポートにすることで、同じフォルダ内のGameCogをエディタが解決しやすくなります
    from .game import GameCog

class DiscussionView(discord.ui.View):
    def __init__(self, timeout):
        super().__init__(timeout=timeout)
        self.ready_players = set()
        self.skip_event = asyncio.Event()

    @discord.ui.button(label="投票に進む", style=discord.ButtonStyle.secondary)
    async def ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        # guildの存在を確認することで、userがMemberであることをエディタに確信させます
        guild = interaction.guild
        user = interaction.user
        
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
    # 【アイテム効果】「沈黙の御札」を貼られている人はミュートを解除しない
    alive_listeners = []
    for p in game.alive_players:
        if isinstance(p, discord.Member):
            if p.id in game.silenced_players:
                try:
                    await p.edit(mute=True) # VCミュート維持
                except: pass
                await channel.send(f"🤐 **{p.display_name} さんは「沈黙の御札」の呪いにより、今日の議論での発言・チャットが禁止されています！**")
            else:
                alive_listeners.append(p)
            
    # 呪いにかかっていない生存者のミュートを解除
    for p in alive_listeners:
        if isinstance(p, discord.Member):
            try:
                await p.edit(mute=False)
            except Exception as e:
                print(f"⚠️ ミュート解除失敗 ({p.display_name}): {e}")

    await channel.send(f"💬 昼の議論を開始します。時間は {game.discussion_time} 秒です。生存者の皆さんは話し合ってください！")
    if game.log_channel:
        await game.log_channel.send("💬 昼の議論フェーズに入りました。")
    
    # スキップボタンの表示
    view = DiscussionView(timeout=float(game.discussion_time))
    alive_count = len(game.alive_players)
    needed = (alive_count // 2) + 1
    
    # 最初のボタンを取得してラベルを更新
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.label = f"投票に進む (0/{needed})"
            break

    await channel.send("💡 議論を切り上げて投票に進むには、下のボタンを押してください（過半数の賛成が必要）。", view=view)
    
    await view.skip_event.wait()

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
