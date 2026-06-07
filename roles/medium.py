from roles.base import BaseRole
class Medium(BaseRole):
    name, team = "霊媒師", "村人"
    def get_action_label(self): return "霊媒"