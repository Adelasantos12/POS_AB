# Django ASGI adapter for supervisor
# This file allows Django to be run with uvicorn via the existing supervisor config

import os
import sys

# Add the parent directory to the path so Django can find the project
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adele_pos.settings')

from django.core.asgi import get_asgi_application
app = get_asgi_application()
