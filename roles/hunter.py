from roles.base import BaseRole
class Hunter(BaseRole):
    name, team = "狩人", "村人"
    def get_action_label(self): return "護衛"
