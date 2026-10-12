"""
Local development settings for SafeHaul.
"""
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Allow all origins locally for development ease
CORS_ALLOW_ALL_ORIGINS = True
