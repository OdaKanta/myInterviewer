"""
WSGI config for learning_interview project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'learning_interview.settings')

application = get_wsgi_application()
