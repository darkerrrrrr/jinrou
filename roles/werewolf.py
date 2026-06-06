from roles.base import BaseRole
class Werewolf(BaseRole):
    name, team = "人狼", "人狼"
    def get_action_label(self): return "襲撃"