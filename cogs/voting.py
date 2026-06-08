import discord, random
from config import game, RoleName
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cogs.game import GameCog

# アイテムシステム関連
from cogs.item import get_player_item, use_player_item


async def start_voting(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    投票フェーズを開始する
    
    Args:
        channel: メインチャンネル
    """
    await channel.send("🗳️ 生存者はメニューから本日追放するプレイヤーを1人選んで投票してください。")
    if game.log_channel:
        await game.log_channel.send("🗳️ 投票フェーズに入りました。")
    
    view = discord.ui.View(timeout=60)
    select_options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.alive_players]
    
    # 投票の詳細を記録 {投票者ID: (ターゲットID, 票の強さ)}
    vote_details = {}
    voted_user_ids = set() # 実際に投票を完了した人のID
    banned_voters = set() # 投票権を剥奪されたプレイヤー

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
            
            use_player_item(self.voter.id)
            self.used = True
            await button_interaction.response.defer()
            
            # アイテム効果を適用
            if self.item_name == "🍯 泥団子":
                banned_voters.add(self.target_member.id)
                # 既に投票済みなら、その票を無効化（削除）する
                if self.target_member.id in vote_details:
                    del vote_details[self.target_member.id]
                    voted_user_ids.discard(self.target_member.id)
                
                try:
                    await self.target_member.send(f"🍯 **【泥団子】** {self.voter.display_name} さんから泥団子を投げられました！")
                except: pass
                
                if game.log_channel:
                    await game.log_channel.send(f"🍯 {self.voter.display_name} が {self.target_member.display_name} の投票権を剥奪しました。")
                await channel.send(f"🍯 **【泥団子発動】** {self.voter.display_name} さんが {self.target_member.display_name} さんに泥団子を投げつけ、今日の投票権を奪いました！")
            elif self.item_name == "🤐 沈黙の御札":
                game.silenced_players.add(self.target_member.id)
                if game.log_channel:
                    await game.log_channel.send(f"🤐 {self.voter.display_name} が {self.target_member.display_name} に翌日の沈黙呪いを付与しました。")
                await channel.send(f"🤐 **【沈黙の御札発動】** {self.voter.display_name} さんが {self.target_member.display_name} さんに呪いの札を貼りました！明日彼は喋れません。")
            elif self.item_name == "🧪 疑惑の劇薬":
                if game.log_channel:
                    await game.log_channel.send(f"🧪 {self.voter.display_name} は「疑惑の劇薬」により2票分を投票しました。")
                await channel.send(f"🧪 **【疑惑の劇薬発動】** {self.voter.display_name} さんの投票が2票分としてカウントされます！")
            
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
            if not isinstance(voter, discord.Member) or voter not in game.alive_players:
                return await interaction.response.send_message("生存者のみ投票可能です。", ephemeral=True)
            
            voter_id = voter.id
            if voter_id in banned_voters:
                return await interaction.response.send_message("泥団子を投げられたため、投票権がありません。", ephemeral=True)
            if voter_id in voted_user_ids:
                 return await interaction.response.send_message("既に投票済みです。", ephemeral=True)
            
            target_id = int(self.values[0])
            guild = interaction.guild
            if not guild: return

            try:
                target_member = guild.get_member(target_id) or await guild.fetch_member(target_id)
            except Exception as e:
                print(f"⚠️ プレイヤー取得失敗 (ID: {target_id}): {e}")
                return await interaction.response.send_message("対象のプレイヤーが見つかりません。", ephemeral=True)
            
            if target_member == voter:
                return await interaction.response.send_message("自分自身には投票できません。", ephemeral=True)

            item_was_used = False
            # アイテムを持ってるかチェック
            player_item = get_player_item(voter_id)
            if player_item and player_item in ["🍯 泥団子", "🤐 沈黙の御札", "🧪 疑惑の劇薬"]:
                # アイテム使用確認
                item_view = ItemUsageView(voter, target_member, player_item)
                await interaction.response.send_message(
                    f"🎁 アイテムを持っています: **{player_item}**\n使用しますか？",
                    view=item_view,
                    ephemeral=True
                )
                await item_view.wait()
                item_was_used = item_view.used
            else:
                await interaction.response.defer(ephemeral=True)
            
            # 疑惑の劇薬を「実際に使用した」場合のみ2票分としてカウント
            vote_power = 2 if (item_was_used and player_item == "🧪 疑惑の劇薬") else 1
            
            # 【狂人の混乱効果】混乱状態のプレイヤーは投票先がランダムになる
            if voter_id in game.confused_players:
                targets = [p for p in game.alive_players if p != voter]
                if not targets:
                    random_target = voter
                else:
                    random_target = random.choice(targets)
                target_id = random_target.id
                target_member = random_target
                if game.log_channel:
                    await game.log_channel.send(f"🌀 {voter.display_name} は混乱しており、投票先が {target_member.display_name} に変更されました。")
            
            voted_user_ids.add(voter_id)
            vote_details[voter_id] = (target_id, vote_power)
            await interaction.followup.send(f"【{voter.display_name}】さんが投票しました。", ephemeral=True)
            
            # 生存者のうち、投票権のある全員が投票したら終了
            if len(voted_user_ids) >= len([p for p in game.alive_players if p.id not in banned_voters]):
                view.stop()

    select_menu = VoteSelect(placeholder="追放するプレイヤーを選択...", options=select_options)
    view.add_item(select_menu)
    
    vote_msg = await channel.send("👇 ここから投票してください", view=view)
    
    await view.wait()
    try:
        await vote_msg.edit(content="🗳️ 投票が締め切られました。", view=None)
    except Exception as e:
        print(f"⚠️ 投票メッセージ編集失敗: {e}")

    # 投票しなかった人の発表
    non_voters = [p for p in game.alive_players if p.id not in voted_user_ids and p.id not in banned_voters]
    if non_voters:
        await channel.send(f"⌛ **投票時間終了**\n未投票者: {', '.join([p.mention for p in non_voters])}\n(棄権は村の議論を停滞させます！)")

    # 最終的な集計
    final_tally = {} # {ターゲットID: 合計票数}
    for v_id, (t_id, power) in vote_details.items():
        final_tally[t_id] = final_tally.get(t_id, 0) + power

    if not final_tally:
        await channel.send("誰も投票しなかったため、本日の処刑は行われません。")
        if game.log_channel:
            await game.log_channel.send("🗳️ 投票がなかったため、処刑なし。")
    elif channel.guild:
        guild = channel.guild
        # 投票結果の表示（内訳）
        result_details = "📊 **投票結果の内訳:**\n"
        for t_id, count in final_tally.items():
            t_member = guild.get_member(t_id)
            name = t_member.display_name if t_member else f"不明({t_id})"
            result_details += f"・{name}: {count} 票\n"
        await channel.send(result_details)

        max_votes_count = max(final_tally.values())
        most_voted_ids = [pid for pid, v in final_tally.items() if v == max_votes_count]
        
        # 🛠️ 同票ランダム処刑（運命のダイス）の処理
        if len(most_voted_ids) > 1:
            await channel.send("⚖️ 投票の結果、最多得票者が同数で並びました……！\n村の意見が割れたため、**運命のダイス（ランダム）**によって追放者が決定されます。")
            most_voted_id = random.choice(most_voted_ids) 
            if game.log_channel:
                await game.log_channel.send(f"🎲 同票（得票数: {max_votes_count}）のため、ランダム抽選を行いました。")
        else:
            most_voted_id = most_voted_ids[0]

        executed_user = guild.get_member(most_voted_id)
        if not executed_user:
            try:
                executed_user = await guild.fetch_member(most_voted_id)
            except Exception as e:
                print(f"⚠️ 処刑対象プレイヤー取得失敗 (ID: {most_voted_id}): {e}")
                await channel.send("⚠️ 処刑対象のプレイヤー情報を取得できませんでした。")
                return

        if isinstance(executed_user, discord.Member) and executed_user in game.alive_players:
            game.alive_players.remove(executed_user)
            game.last_executed = executed_user  
            await channel.send(f"⚖️ 運命の審判により、本日は 【**{executed_user.display_name}**】 が村から追放されました。")
            if game.log_channel:
                await game.log_channel.send(f"⚖️ 処刑: {executed_user.display_name} (総投票ポイント: {max_votes_count})")
            await channels.handle_player_death_vc(executed_user)

    if await self.check_game_over(channel): 
        return

    await self.start_night(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
