import discord
class BaseRole:
    def __init__(self, player=None): self.player = player
    name, team, has_night_action = "平民", "村人", False
    async def send_night_menu(self, alive_players): pass
