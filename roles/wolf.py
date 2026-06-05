# roles/wolf.py
import discord
from roles.base import BaseRole
from config import game

class Werewolf(BaseRole):
    name = "人狼"
    team = "人狼"
    has_night_action = True

    async def send_night_menu(self, alive_players):
        from views import RoleActionView
        
        # 相方人狼をリスト化
        teammates = []
        for member, role_obj in game.roles.items():
            if role_obj.name == "人狼" and member != self.player and member in alive_players:
                teammates.append(member.display_name)
        
        if teammates:
            teammate_info = f"仲間（相方人狼）: {', '.join(teammates)}\n💬 ※このDMへ自由に発言すると、相方にメッセージが自動転送されます。"
        else:
            teammate_info = "仲間（相方人狼）: なし（孤独な一匹狼です）"

        # 自分以外を襲撃ターゲットにする
        targets = [p for p in alive_players if p != self.player]
        view = RoleActionView(actor=self.player, targets=targets, placeholder="襲撃する相手を1人選んでください")
        
        await self.player.send(
            f"🐺【人狼の夜行動】\n"
            f"📋 {teammate_info}\n\n"
            f"今夜は誰を襲撃しますか？下のセレクトメニューから選んでください。", 
            view=view
        )