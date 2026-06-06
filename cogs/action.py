import discord, sys, os
sys.path.append(os.getcwd())
from config import game

class ActionSelect(discord.ui.Select):
    def __init__(self, actor, action_label):
        self.actor = actor
        self.action_label = action_label
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) 
                   for p in game.alive_players if p != actor]
        super().__init__(placeholder=f"{action_label}先を選択...", options=options)

    async def callback(self, interaction: discord.Interaction):
        target = next((p for p in game.alive_players if p.id == int(self.values[0])), None)
        game.actions[self.actor] = {"target": target, "action": self.action_label}
        await interaction.response.send_message(f"{target.display_name} を{self.action_label}しました。", ephemeral=True)

class ActionView(discord.ui.View):
    def __init__(self, actor, action_label):
        super().__init__(timeout=60)
        self.add_item(ActionSelect(actor, action_label))
