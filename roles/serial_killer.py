from roles.base import BaseRole
class SerialKiller(BaseRole):
    name, team = "シリアルキラー", "シリアルキラー"
    def get_action_label(self): return "殺害"