import os

class ProjectManager:
    """
    Manages workspace project directories and active project tracking.
    """
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.active_project = None

    def reinit(self):
        """Re-initializes project manager state."""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))

    def list_projects(self):
        projects = []
        if os.path.exists(self.base_dir):
            try:
                for entry in os.listdir(self.base_dir):
                    full_path = os.path.join(self.base_dir, entry)
                    if os.path.isdir(full_path) and not entry.startswith('.') and entry not in ['venv', '__pycache__', 'templates', 'static']:
                        projects.append(entry)
            except Exception as e:
                print(f"[ProjectManager] Error listing projects: {e}")
        return sorted(projects)

    def create_project(self, name):
        if not name or '..' in name or '/' in name or '\\' in name:
            raise ValueError("Invalid project name")
        
        project_dir = os.path.join(self.base_dir, name)
        if os.path.exists(project_dir):
            raise FileExistsError("Project already exists")
        
        os.makedirs(project_dir, exist_ok=True)
        return project_dir

    def set_active_project(self, name):
        if not name:
            self.active_project = None
            return self.base_dir
        
        if '..' in name or '/' in name or '\\' in name:
            raise ValueError("Invalid project name")
        
        project_dir = os.path.join(self.base_dir, name)
        if not os.path.isdir(project_dir):
            raise FileNotFoundError(f"Project directory '{name}' does not exist")
        
        self.active_project = name
        return project_dir

    def get_active_workspace_path(self):
        if self.active_project:
            p = os.path.join(self.base_dir, self.active_project)
            if os.path.isdir(p):
                return p
        return self.base_dir
