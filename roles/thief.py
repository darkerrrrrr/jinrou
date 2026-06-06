from roles.base import BaseRole
class Thief(BaseRole):
    name, team = "怪盗", "村人"
    def get_action_label(self): return "盗む"
