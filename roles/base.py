# roles/base.py
import discord

class BaseRole:
    name = "平民"
    team = "村人"  # "村人", "人狼", "シリアルキラー" など
    has_night_action = False

    def __init__(self, player: discord.Member):
        self.player = player

    async def send_night_menu(self, alive_players):
        """夜の行動メニューをDMに送信する（デフォルトは何もしない役職用）"""
        if not self.has_night_action:
            await self.player.send(f"🌙【{self.name}の夜行動】\n現在夜のフェーズです。あなたの役職は夜の行動がありません。恐ろしい夜が明けるのを待ちましょう...")