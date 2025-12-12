import os
from celery import Celery

# Django設定モジュールをCeleryに設定
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'learning_interview.settings')

app = Celery('learning_interview')

# Djangoの設定からCeleryの設定を読み込み
app.config_from_object('django.conf:settings', namespace='CELERY')

# Djangoアプリからタスクを自動検出
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
