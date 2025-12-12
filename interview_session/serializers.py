from rest_framework import serializers
from .models import InterviewSession, Explanation, Question, Answer, SessionTimeoutTimer
from knowledge_tree.serializers import KnowledgeNodeSerializer


class InterviewSessionSerializer(serializers.ModelSerializer):
    current_node = KnowledgeNodeSerializer(read_only=True)
    
    class Meta:
        model = InterviewSession
        fields = [
            'id', 'user', 'material', 'status', 'current_node',
            'started_at', 'ended_at'
        ]
        read_only_fields = ['user', 'started_at']


class ExplanationSerializer(serializers.ModelSerializer):
    topics_mentioned = KnowledgeNodeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Explanation
        fields = [
            'id', 'session', 'content', 'audio_file', 'topics_mentioned',
            'created_at'
        ]


class QuestionSerializer(serializers.ModelSerializer):
    node = KnowledgeNodeSerializer(read_only=True)
    
    class Meta:
        model = Question
        fields = [
            'id', 'session', 'node', 'content', 'question_type',
            'depth_level', 'context_chunks', 'created_at'
        ]


class AnswerSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    
    class Meta:
        model = Answer
        fields = [
            'id', 'question', 'content', 'audio_file', 'understanding_score',
            'needs_deeper_questioning', 'created_at'
        ]


class SessionTimeoutTimerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionTimeoutTimer
        fields = [
            'id', 'session', 'question', 'start_time', 'timeout_seconds',
            'is_active'
        ]
