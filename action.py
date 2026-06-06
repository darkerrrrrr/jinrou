import discord
from config import game

class ActionView(discord.ui.View):
    def __init__(self, actor, action_label):
        super().__init__(timeout=60)
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) 
                   for p in game.alive_players if p != actor]
        select = discord.ui.Select(placeholder=f"{action_label}先を選択...", options=options)
        
        async def callback(interaction):
            target = next((p for p in game.alive_players if p.id == int(select.values[0])), None)
            game.actions[actor] = {"target": target, "action": action_label}
            await interaction.response.send_message(f"{target.display_name} を{action_label}します。", ephemeral=True)
            
        select.callback = callback
        self.add_item(select)
