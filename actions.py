import discord
from config import game

class ActionView(discord.ui.View):
    def __init__(self, player, label):
        super().__init__(timeout=None)
        self.player = player
        self.label = label

    @discord.ui.button(label="選択", style=discord.ButtonStyle.primary)
    async def select_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ここに選択時の処理を記述します
        game.actions[self.player] = {'action': self.label, 'target': interaction.user}
        await interaction.response.send_message(f"{self.label}先を決定しました。", ephemeral=True)