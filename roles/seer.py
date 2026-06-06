from roles.base import BaseRole
class Seer(BaseRole):
    name, team = "占い師", "村人"
    def get_action_label(self): return "占い"
