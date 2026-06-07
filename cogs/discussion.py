import discord, asyncio
from config import game
import channels

# アイテムシステム関連
from cogs.item import silenced_players


async def start_discussion(self, channel):
    """昼の議論フェーズを開始"""
    # 【アイテム効果】「沈黙の御札」を貼られている人はミュートを解除しない
    alive_listeners = []
    for p in game.alive_players:
        if p.id in silenced_players:
            try:
                await p.edit(mute=True) # VCミュート維持
            except: pass
            await channel.send(f"🤐 **{p.display_name} さんは「沈黙の御札」の呪いにより、今日の議論での発言・チャットが禁止されています！**")
        else:
            alive_listeners.append(p)
            
    # 呪いにかかっていない生存者のミュートを解除
    for p in alive_listeners:
        try:
            await p.edit(mute=False)
        except: pass

    await channel.send(f"💬 昼の議論を開始します。時間は {game.discussion_time} 秒です。生存者の皆さんは話し合ってください！")
    await game.log_channel.send("💬 昼の議論フェーズに入りました。")
    
    await asyncio.sleep(game.discussion_time)
    
    await channels.mute_all_alive_players(mute_status=True)
    # 昼フェーズ後に沈黙の呪いをクリア（翌昼には効果がなくなる）
    silenced_players.clear() 

    await channel.send("⏱️ 議論時間が終了しました。これより投票（処刑対象の選出）に移ります。")
    await self.start_voting(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
