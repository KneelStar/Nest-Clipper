import os
import sys
import tkinter as tk
from app_prefs_database import DatabaseHandler, check_database_exists, get_db_path
from auth_app_ui import NestClipperApp
from nest_clipper_backend import is_user_authed
from pre_auth_app_ui import PreAuthNestClipperApp

def resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

if __name__ == "__main__":
    root = tk.Tk()
    icon_path = resource_path("resources/Nest Clipper Logo.png")
    icon_image = tk.PhotoImage(file=icon_path)
    root.iconphoto(False, icon_image)

    if is_user_authed():
        app = NestClipperApp(root)
        root.mainloop()

    else:
        app = PreAuthNestClipperApp(root)
        root.mainloop()
