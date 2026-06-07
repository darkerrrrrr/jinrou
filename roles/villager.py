from roles.base import BaseRole
class Villager(BaseRole):
    name, team = "村人", "村人"
    def get_action_label(self): return None