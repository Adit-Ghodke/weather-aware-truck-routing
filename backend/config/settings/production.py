"""
Production settings for SafeHaul deployment on Google Cloud Run.
"""
from .base import *

DEBUG = False

# Strict production security headers
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Cloud Run terminates TLS at Google's front-end proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
