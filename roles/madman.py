from roles.base import BaseRole
class Madman(BaseRole):
    name, team = "狂人", "人狼"
    def get_action_label(self): return "混乱"