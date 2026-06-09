import discord, random, asyncio
from config import get_game, RoleName
import channels
from typing import TYPE_CHECKING, Optional, cast
if TYPE_CHECKING:
    from cogs.game import GameCog

# アイテムシステム関連
from cogs.item import get_player_item, use_player_item

class DodgeView(discord.ui.View):
    """アイテム攻撃を回避するためのクイック・タイム・ビュー"""
    def __init__(self, timeout: int = 4):
        super().__init__(timeout=timeout)
        self.success = False

    @discord.ui.button(label="🛡️ 回避する！", style=discord.ButtonStyle.danger)
    async def dodge(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.success = True
        self.stop()
        await interaction.response.send_message("✨ 見事に回避した！", ephemeral=True)

class DuelView(discord.ui.View):
    """同票時に生存を賭けて戦うクリック・バトル・ビュー"""
    def __init__(self, participants: list[discord.Member]):
        super().__init__(timeout=15)
        self.winner: Optional[discord.Member] = None
        for p in participants:
            btn = discord.ui.Button(label=f"🛡️ {p.display_name}", style=discord.ButtonStyle.primary, custom_id=str(p.id))
            btn.callback = self.make_callback(p)
            self.add_item(btn)

    def make_callback(self, player: discord.Member):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != player.id:
                return await interaction.response.send_message("❌ これはあなたのボタンではありません！", ephemeral=True)
            self.winner = player
            self.stop()
            # ボタンをすべて無効化
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            await interaction.response.edit_message(view=self)
        return callback

class ItemUsageView(discord.ui.View):
    def __init__(self, voter: discord.Member, target_member: discord.Member, item_name: str):
        super().__init__(timeout=30)
        self.voter: discord.Member = voter
        self.target_member: discord.Member = target_member
        self.item_name: str = item_name
        self.used: bool = False

    @discord.ui.button(label="アイテムを使う", style=discord.ButtonStyle.success)
    async def use_item(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        if button_interaction.user != self.voter:
            return await button_interaction.response.send_message("このボタンは使用できません。", ephemeral=True)
        
        game = get_game(button_interaction.guild.id)
        target_channel = game.progress_channel or button_interaction.channel
        use_player_item(button_interaction.guild.id, self.voter.id)
        self.used = True
        await button_interaction.response.defer()

        # ⚡ アクション要素：回避チャンスの発生（泥団子と沈黙のみ）
        dodge_success = False
        if self.item_name in ["🍯 泥団子", "🤐 沈黙の御札"]:
            dodge_view = DodgeView(timeout=4)
            try:
                d_embed = discord.Embed(title="⚠️ 攻撃検知！", description="誰かがあなたにアイテムを使おうとしています！\n**4秒以内**に下のボタンを押して回避してください！", color=discord.Color.red())
                d_msg = await self.target_member.send(embed=d_embed, view=dodge_view)
                await dodge_view.wait()
                dodge_success = dodge_view.success
                await d_msg.edit(view=None)
            except discord.Forbidden:
                print(f"❌ 権限不足: {self.target_member.display_name} へのDM送信に失敗しました。BotにDM送信権限があるか確認してください。")
            except Exception: pass

        if dodge_success:
            await target_channel.send(embed=discord.Embed(description=f"💨 **【回避成功】** {self.target_member.mention} さんが反射神経で {self.item_name} をかわしました！", color=discord.Color.blue()), silent=True)
            self.stop()
            return
        
        # アイテム効果を適用
        if self.item_name == "🍯 泥団子":
            game.banned_voters.add(self.target_member.id)
            if self.target_member.id in game.vote_details:
                del game.vote_details[self.target_member.id]
                game.voted_user_ids.discard(self.target_member.id)
            
            try:
                dm_embed = discord.Embed(title="🍯 泥団子を投げられました！", description=f"{self.voter.display_name} さんから泥団子を投げられ、投票権を奪われました。", color=discord.Color.dark_orange())
                await self.target_member.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"❌ 権限不足: {self.target_member.display_name} へのDM送信に失敗しました。BotにDM送信権限があるか確認してください。")
            except Exception: pass
            
            await game.save_state(button_interaction.guild)
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"🍯 {self.voter.display_name} が {self.target_member.display_name} の投票権を剥奪。", color=discord.Color.dark_orange()))
            await target_channel.send(embed=discord.Embed(description=f"🍯 **【泥団子発動】** {self.voter.mention} さんが {self.target_member.mention} さんの投票権を奪いました！", color=discord.Color.dark_orange()), silent=True)
        elif self.item_name == "🤐 沈黙の御札":
            game.silenced_players.add(self.target_member.id)
            await game.save_state(button_interaction.guild)
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"🤐 {self.voter.display_name} が {self.target_member.display_name} に翌日の沈黙呪いを付与。", color=discord.Color.dark_grey()))
            await target_channel.send(embed=discord.Embed(description=f"🤐 **【沈黙の御札発動】** {self.voter.mention} さんが {self.target_member.mention} さんに呪いの札を貼りました！", color=discord.Color.dark_grey()), silent=True)
        elif self.item_name == "🧪 疑惑の劇薬":
            await game.save_state(button_interaction.guild)
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"🧪 {self.voter.display_name} は疑惑の劇薬により2票分を投票。", color=discord.Color.purple()))
            await target_channel.send(embed=discord.Embed(description=f"🧪 **【疑惑の劇薬発動】** {self.voter.mention} さんの投票は2票分として集計されます！", color=discord.Color.purple()), silent=True)
        
        self.stop()

    @discord.ui.button(label="使わない", style=discord.ButtonStyle.secondary)
    async def skip_item(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        if button_interaction.user != self.voter:
            return await button_interaction.response.send_message("このボタンは使用できません。", ephemeral=True)
        await button_interaction.response.defer()
        self.stop()

class VoteSelect(discord.ui.Select):
    async def callback(self, interaction: discord.Interaction):
        voter = interaction.user
        game = get_game(interaction.guild.id)
        if not isinstance(voter, discord.Member) or voter not in game.alive_players:
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 生存者のみ投票可能です。", color=discord.Color.red()), ephemeral=True)
        
        voter_id = voter.id
        if voter_id in game.banned_voters:
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 泥団子を投げられたため、投票権がありません。", color=discord.Color.red()), ephemeral=True)
        if voter_id in game.voted_user_ids:
             return await interaction.response.send_message(embed=discord.Embed(description="⚠️ 既に投票済みです。", color=discord.Color.orange()), ephemeral=True)
        
        target_id = int(self.values[0])
        guild = interaction.guild
        if not guild: return

        try:
            target_member = guild.get_member(target_id) or await guild.fetch_member(target_id)
        except Exception as e:
            print(f"⚠️ プレイヤー取得失敗 (ID: {target_id}): {e}")
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 対象のプレイヤーが見つかりません。", color=discord.Color.red()), ephemeral=True)
        
        if target_member == voter and len(game.alive_players) > 1:
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 自分自身には投票できません。", color=discord.Color.red()), ephemeral=True)

        item_was_used = False
        player_item = get_player_item(interaction.guild.id, voter_id)
        has_voting_item = bool(player_item and player_item in ["🍯 泥団子", "🤐 沈黙の御札", "🧪 疑惑の劇薬"])

        if has_voting_item:
            item_view = ItemUsageView(voter, target_member, str(player_item))
            item_embed = discord.Embed(title="🎁 アイテム使用確認", description=f"アイテム **{player_item}** を持っています。\n{target_member.mention} さんに対して使用しますか？", color=discord.Color.blue())
            await interaction.response.send_message(embed=item_embed, view=item_view, ephemeral=True)
            await item_view.wait()
            item_was_used = bool(item_view.used)
        else:
            await game.save_state(guild)
            await interaction.response.defer(ephemeral=True)
        
        vote_power = 2 if (item_was_used and player_item == "🧪 疑惑の劇薬") else 1
        game.voted_user_ids.add(voter_id)
        game.vote_details[voter_id] = [target_id, vote_power]
        await game.save_state(guild)
        await interaction.followup.send(embed=discord.Embed(description=f"✅ 【{target_member.display_name}】さんへの投票を受け付けました。", color=discord.Color.green()), ephemeral=True)
        if len(game.voted_user_ids) >= len([p for p in game.alive_players if p.id not in game.banned_voters]):
            self.view.stop()

async def start_voting(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    投票フェーズを開始する
    
    Args:
        channel: メインチャンネル
    """
    game = get_game(channel.guild.id)
    game.event_log.append(f"═══ {game.day_count}日目：投票 ═══")
    target_channel = game.progress_channel or channel

    await target_channel.send(embed=discord.Embed(title="🗳️ 投票開始", description="本日追放するプレイヤーを1人選んで投票してください。", color=discord.Color.gold()), silent=True)
    await game.save_state(channel.guild)
    if game.log_channel:
        await game.log_channel.send(embed=discord.Embed(description="🗳️ 投票フェーズに入りました。", color=discord.Color.gold()))
    
    # ⚠️ 安全策：生存者がいない場合は投票をスキップして終了チェックへ
    if not game.alive_players:
        await self.check_game_over(channel)
        return

    view = discord.ui.View(timeout=60)
    select_options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.alive_players]

    select_menu = VoteSelect(placeholder="追放するプレイヤーを選択...", options=select_options)
    view.add_item(select_menu)
    
    vote_msg = await target_channel.send(embed=discord.Embed(description="👇 下のメニューから投票してください", color=discord.Color.blue()), view=view)
    
    await view.wait()
    try:
        await vote_msg.edit(embed=discord.Embed(description="🗳️ 投票が締め切られました。", color=discord.Color.light_grey()), view=None)
    except Exception as e:
        print(f"⚠️ 投票メッセージ編集失敗: {e}")

    # 投票しなかった人の発表
    non_voters = [p for p in game.alive_players if p.id not in game.voted_user_ids and p.id not in game.banned_voters]
    if non_voters:
        nv_embed = discord.Embed(title="⌛ 投票終了", description=f"未投票者: {', '.join([p.mention for p in non_voters])}\n※棄権は村を滅ぼす原因となります！", color=discord.Color.red())
        await target_channel.send(embed=nv_embed, silent=True)

    # 最終的な集計
    final_tally = {} # {ターゲットID: 合計票数}
    for v_id, (t_id, power) in game.vote_details.items():
        final_tally[t_id] = final_tally.get(t_id, 0) + power

    if not final_tally:
        await target_channel.send(embed=discord.Embed(description="誰も投票しなかったため、本日の処刑は行われません。", color=discord.Color.light_grey()), silent=True)
        if game.log_channel:
            await game.log_channel.send(embed=discord.Embed(description="🗳️ 投票がなかったため、処刑なし。", color=discord.Color.light_grey()))
    elif channel.guild:
        guild = channel.guild
        # 投票結果の表示（内訳）
        result_details = ""
        for t_id, count in final_tally.items():
            t_member = guild.get_member(t_id)
            name = t_member.display_name if t_member else f"不明({t_id})"
            result_details += f"・{name}: {count} 票\n"
        
        await target_channel.send(embed=discord.Embed(title="📊 投票結果の内訳", description=result_details, color=discord.Color.blue()), silent=True)

        max_votes_count = max(final_tally.values())
        most_voted_ids = [pid for pid, v in final_tally.items() if v == max_votes_count]
        
        # 🛠️ 同票時の決闘（アクション要素：クリックバトル）
        if len(most_voted_ids) > 1:
            duel_targets = [guild.get_member(pid) for pid in most_voted_ids if guild.get_member(pid)]
            if len(duel_targets) >= 2:
                duel_embed = discord.Embed(title="⚔️ 決選投票：生存競争", description="得票数が並びました！これより生存を賭けたバトルを開始します。\n**自分の名前のボタンを誰よりも早く押した者**が、追放を免れます！", color=discord.Color.dark_red())
                view = DuelView(duel_targets)
                duel_msg = await target_channel.send(embed=duel_embed, view=view)
                await view.wait()
                
                if view.winner:
                    await target_channel.send(embed=discord.Embed(description=f"⚡ {view.winner.mention} が凄まじい反応速度で追放を免れました！", color=discord.Color.green()))
                    most_voted_ids = [pid for pid in most_voted_ids if pid != view.winner.id]
                
                # 生き残った人以外からランダムに選ぶ
                most_voted_id = random.choice(most_voted_ids)
            else:
                most_voted_id = random.choice(most_voted_ids)
        else:
            most_voted_id = most_voted_ids[0]

        executed_user = guild.get_member(most_voted_id)
        if not executed_user:
            try:
                executed_user = await guild.fetch_member(most_voted_id)
            except Exception as e:
                print(f"⚠️ 処刑対象プレイヤー取得失敗 (ID: {most_voted_id}): {e}")
                await target_channel.send(embed=discord.Embed(description="⚠️ 処刑対象のプレイヤー情報を取得できませんでした。", color=discord.Color.red()), silent=True)
                return

        if isinstance(executed_user, discord.Member) and executed_user in game.alive_players:
            game.alive_players.remove(executed_user)
            game.last_executed = executed_user  
            await target_channel.send(embed=discord.Embed(title="⚖️ 処刑執行", description=f"本日の追放者は 【**{executed_user.display_name}**】 に決定しました。", color=discord.Color.dark_red()), silent=True)
            game.event_log.append(f"⚖️ 追放：{executed_user.display_name}")
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"⚖️ 処刑: {executed_user.display_name} ({max_votes_count}票)", color=discord.Color.dark_red()))
            await channels.handle_player_death_vc(executed_user, guild)

    if await self.check_game_over(channel): 
        return

    # 処刑結果を確認し、夜の準備をする時間を少し作る
    await asyncio.sleep(10)
    await self.start_night(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
