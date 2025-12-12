from django.urls import path
from . import views

urlpatterns = [
    path('generate/', views.generate_next_question, name='generate_next_question'),
    path('evaluate/', views.evaluate_answer, name='evaluate_answer'),
    path('progress/', views.get_session_progress, name='get_session_progress'),
    path('skip/', views.skip_current_topic, name='skip_current_topic'),
]
