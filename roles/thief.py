# roles/thief.py
import discord
from roles.base import BaseRole

class Thief(BaseRole):
    name = "怪盗"
    team = "村人"
    has_night_action = True

    async def send_thief_menu(self, all_players):
        """1日目の夜の最初にGameCogから呼び出される専用メニュー"""
        from views import ThiefView
        # 自分以外の「ゲームに参加している全プレイヤー」から盗める
        targets = [p for p in all_players if p != self.player]
        
        view = ThiefView(targets=targets)
        await self.player.send(
            f"🕵️【怪盗の夜行動（最初の夜限定）】\n"
            f"役職を盗み取るターゲットを1人選んでください。\n"
            f"※選んだ瞬間に即座に役職が入れ替わり、新しい役職がDMに通知されます。",
            view=view
        )