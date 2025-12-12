"""
ASGI config for learning_interview project.

現在はHTTPのみ使用（WebSocketは未使用）
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'learning_interview.settings')

# HTTPのみのシンプルなASGI設定
application = get_asgi_application()

# WebSocket設定（現在未使用）
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# import interview_session.routing
# 
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AuthMiddlewareStack(
#         URLRouter(
#             interview_session.routing.websocket_urlpatterns
#         )
#     ),
# })
