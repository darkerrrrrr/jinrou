import discord
from config import game

class ActionSelect(discord.ui.Select):
    def __init__(self, actor, action_label):
        self.actor = actor
        self.action_label = action_label
        options = [
            discord.SelectOption(label=p.display_name, value=str(p.id)) 
            for p in game.alive_players if p != actor
        ]
        super().__init__(placeholder="対象のプレイヤーを選択...", options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        target_user = interaction.client.get_user(target_id)
        if not target_user:
            target_user = await interaction.client.fetch_user(target_id)
        
        game.actions[self.actor] = {"action": self.action_label, "target": target_user}
        await interaction.response.edit_message(content=f"選択完了: 【{target_user.display_name}】に「{self.action_label}」を行います。", view=None)

class ActionView(discord.ui.View):
    def __init__(self, actor, action_label):
        super().__init__(timeout=60)
        self.add_item(ActionSelect(actor, action_label))