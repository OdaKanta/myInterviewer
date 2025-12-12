from django.contrib import admin
from .models import InterviewSession, Explanation, Question, Answer, SessionTimeoutTimer


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'material', 'status', 'started_at']
    list_filter = ['status', 'started_at']
    readonly_fields = ['started_at']


@admin.register(Explanation)
class ExplanationAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'created_at']
    list_filter = ['created_at']
    readonly_fields = ['created_at']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'node', 'question_type', 'depth_level', 'created_at']
    list_filter = ['question_type', 'depth_level', 'created_at']
    readonly_fields = ['created_at']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['id', 'question', 'understanding_score', 'needs_deeper_questioning', 'created_at']
    list_filter = ['needs_deeper_questioning', 'created_at']
    readonly_fields = ['created_at']


@admin.register(SessionTimeoutTimer)
class SessionTimeoutTimerAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'question', 'timeout_seconds', 'is_active']
    list_filter = ['is_active']
