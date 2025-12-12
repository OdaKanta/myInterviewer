# このファイルは現在使用されていません
# 現在の実装ではOpenAI Realtime APIを直接使用しており、
# Django ChannelsのWebSocketルーティングは使用されていません

# 将来的にWebSocket機能が必要になった場合に備えて保持

"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/interview/(?P<session_id>\w+)/$', consumers.InterviewConsumer.as_asgi()),
]
"""

# 現在は空のリストを返す
websocket_urlpatterns = []
