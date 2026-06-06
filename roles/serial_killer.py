from roles.base import BaseRole
class SerialKiller(BaseRole):
    name, team = "シリアルキラー", "第三陣営"
    def get_action_label(self): return "殺害"
