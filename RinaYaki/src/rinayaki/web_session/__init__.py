"""Optional, app-owned WebView2 login sessions."""

from .launcher import (
    WebSessionProcess, can_open_session, launch_detached_session, launch_session,
)
from .model import SessionTarget, profile_directory, session_target

__all__ = [
    'SessionTarget', 'WebSessionProcess', 'can_open_session',
    'launch_detached_session', 'launch_session', 'profile_directory',
    'session_target',
]
