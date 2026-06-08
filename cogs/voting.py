import discord, random
from config import game
import channels

# アイテムシステム関連
from cogs.item import get_player_item, use_player_item


async def start_voting(self, channel: discord.TextChannel) -> None:
    """
    投票フェーズを開始する
    
    Args:
        channel: メインチャンネル
    """
    await channel.send("🗳️ 生存者はメニューから本日追放するプレイヤーを1人選んで投票してください。")
    await game.log_channel.send("🗳️ 投票フェーズに入りました。")
    
    view = discord.ui.View(timeout=60)
    select_options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.alive_players]
    
    votes = {}
    voted_users = set()

    class ItemUsageView(discord.ui.View):
        def __init__(self, voter, target_member, item_name):
            super().__init__(timeout=30)
            self.voter = voter
            self.target_member = target_member
            self.item_name = item_name

        @discord.ui.button(label="アイテムを使う", style=discord.ButtonStyle.success)
        async def use_item(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user != self.voter:
                return await button_interaction.response.send_message("このボタンは使用できません。", ephemeral=True)
            
            use_player_item(self.voter.id)
            await button_interaction.response.defer()
            
            # アイテム効果を適用
            if self.item_name == "🍯 泥団子":
                voted_users.add(self.target_member)
                await game.log_channel.send(f"🍯 {self.voter.display_name} が {self.target_member.display_name} の投票権を剥奪しました。")
                await channel.send(f"🍯 **【泥団子発動】** {self.voter.display_name} さんが {self.target_member.display_name} さんに泥団子を投げつけ、今日の投票権を奪いました！")
            elif self.item_name == "🤐 沈黙の御札":
                game.silenced_players.add(self.target_member.id)
                await game.log_channel.send(f"🤐 {self.voter.display_name} が {self.target_member.display_name} に翌日の沈黙呪いを付与しました。")
                await channel.send(f"🤐 **【沈黙の御札発動】** {self.voter.display_name} さんが {self.target_member.display_name} さんに呪いの札を貼りました！明日彼は喋れません。")
            elif self.item_name == "🧪 疑惑の劇薬":
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
            if interaction.user not in game.alive_players:
                return await interaction.response.send_message("生存者のみ投票可能です。", ephemeral=True)
            if interaction.user in voted_users:
                return await interaction.response.send_message("既に投票済みです。", ephemeral=True)
            
            target_id = int(self.values[0])
            target_member = interaction.guild.get_member(target_id)
            if not target_member:
                try:
                    target_member = await interaction.guild.fetch_member(target_id)
                except Exception as e:
                    print(f"⚠️ プレイヤー取得失敗 (ID: {target_id}): {e}")
                    return await interaction.response.send_message("対象のプレイヤーが見つかりません。", ephemeral=True)
            
            # アイテムを持ってるかチェック
            player_item = get_player_item(interaction.user.id)
            if player_item and player_item in ["🍯 泥団子", "🤐 沈黙の御札", "🧪 疑惑の劇薬"]:
                # アイテム使用確認
                item_view = ItemUsageView(interaction.user, target_member, player_item)
                await interaction.response.send_message(
                    f"🎁 アイテムを持っています: **{player_item}**\n使用しますか？",
                    view=item_view,
                    ephemeral=True
                )
                await item_view.wait()
            
            # 投票権を持ってるかチェック（泥団子で奪われたら投票できない）
            if interaction.user in voted_users:
                return await interaction.followup.send("投票権がありません。", ephemeral=True)
            
            # 疑惑の劇薬を使ったかチェック（アイテムがもう削除されているので、player_itemで判定）
            vote_power = 2 if player_item == "🧪 疑惑の劇薬" else 1
            
            voted_users.add(interaction.user)
            votes[target_id] = votes.get(target_id, 0) + vote_power
            await interaction.followup.send(f"【{interaction.user.display_name}】さんが投票しました。", ephemeral=True)
            
            if len(voted_users) >= len(game.alive_players):
                view.stop()

    select_menu = VoteSelect(placeholder="追放するプレイヤーを選択...", options=select_options)
    view.add_item(select_menu)
    
    vote_msg = await channel.send("👇 ここから投票してください", view=view)
    
    await view.wait()
    try:
        await vote_msg.edit(content="🗳️ 投票が締め切られました。", view=None)
    except Exception as e:
        print(f"⚠️ 投票メッセージ編集失敗: {e}")

    if not votes:
        await channel.send("誰も投票しなかったため、本日の処刑は行われません。")
        await game.log_channel.send("🗳️ 投票がなかったため、処刑なし。")
    else:
        max_votes_count = max(votes.values())
        most_voted_ids = [pid for pid, v in votes.items() if v == max_votes_count]
        
        # 🛠️ 同票ランダム処刑（運命のダイス）の処理
        if len(most_voted_ids) > 1:
            await channel.send("⚖️ 投票の結果、最多得票者が同数で並びました……！\n村の意見が割れたため、**運命のダイス（ランダム）**によって追放者が決定されます。")
            most_voted_id = random.choice(most_voted_ids) 
            await game.log_channel.send(f"🎲 同票（得票数: {max_votes_count}）のため、ランダム抽選を行いました。")
        else:
            most_voted_id = most_voted_ids[0]

        executed_user = channel.guild.get_member(most_voted_id)
        if not executed_user:
            try:
                executed_user = await channel.guild.fetch_member(most_voted_id)
            except Exception as e:
                print(f"⚠️ 処刑対象プレイヤー取得失敗 (ID: {most_voted_id}): {e}")
                await channel.send("⚠️ 処刑対象のプレイヤー情報を取得できませんでした。")
                return

        if executed_user and executed_user in game.alive_players:
            game.alive_players.remove(executed_user)
            game.last_executed = executed_user  
            await channel.send(f"⚖️ 運命の審判により、本日は 【**{executed_user.display_name}**】 が村から追放されました。")
            await game.log_channel.send(f"⚖️ 処刑: {executed_user.display_name} (総投票ポイント: {max_votes_count})")
            await channels.handle_player_death_vc(executed_user)

    if await self.check_game_over(channel): 
        return

    await self.start_night(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
