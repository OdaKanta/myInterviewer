from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InterviewSessionViewSet, ExplanationViewSet, QuestionViewSet, AnswerViewSet

router = DefaultRouter()
router.register(r'sessions', InterviewSessionViewSet)
router.register(r'explanations', ExplanationViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'answers', AnswerViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
