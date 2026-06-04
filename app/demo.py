from flask import current_app
from flask_login import current_user


def is_read_only_demo_user():
    """Return True when the logged-in user is the configured public demo user."""
    if not getattr(current_user, "is_authenticated", False):
        return False
    demo_user = current_app.config.get("DEMO_READ_ONLY_USERNAME")
    if not demo_user:
        return False
    if not current_app.config.get("DEMO_PUBLIC_LOGIN_ENABLED", False):
        return False
    return getattr(current_user, "username", None) == demo_user
