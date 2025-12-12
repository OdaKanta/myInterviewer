from django.db import models
from django.contrib.auth.models import User
from knowledge_tree.models import KnowledgeNode, LearningMaterial


class InterviewSession(models.Model):
    """インタビューセッション"""
    STATUS_CHOICES = [
        ('preparing', '準備中'),
        ('explaining', '説明フェーズ'),
        ('questioning', '質問フェーズ'),
        ('completed', '完了'),
        ('paused', '一時停止'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="ユーザー")
    material = models.ForeignKey(LearningMaterial, on_delete=models.CASCADE, verbose_name="学習教材")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preparing', verbose_name="ステータス")
    current_node = models.ForeignKey(KnowledgeNode, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="現在のノード")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "インタビューセッション"
        verbose_name_plural = "インタビューセッション"
    
    def __str__(self):
        return f"{self.user.username} - {self.material.title} ({self.status})"


class Explanation(models.Model):
    """学習者の説明"""
    session = models.ForeignKey(
        InterviewSession, on_delete=models.CASCADE,
        related_name='explanations', verbose_name="セッション"
    )
    content = models.TextField(verbose_name="説明内容")
    audio_file = models.FileField(
        upload_to='explanations/', null=True, blank=True,
        verbose_name="音声ファイル"
    )
    topics_mentioned = models.ManyToManyField(
        KnowledgeNode, related_name='mentioned_in_explanations',
        verbose_name="言及されたトピック"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "説明"
        verbose_name_plural = "説明"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Explanation by {self.session.user.username} at {self.created_at}"


class Question(models.Model):
    """質問"""
    QUESTION_TYPE_CHOICES = [
        ('understanding', '理解確認'),
        ('clarification', '明確化'),
        ('elaboration', '詳細化'),
        ('application', '応用'),
        ('connection', '関連性'),
        ('evaluation', '評価'),
        ('follow_up', 'フォローアップ'),
    ]
    
    session = models.ForeignKey(
        InterviewSession, on_delete=models.CASCADE,
        related_name='questions', verbose_name="セッション"
    )
    node = models.ForeignKey(
        KnowledgeNode, on_delete=models.CASCADE, 
        null=True, blank=True, verbose_name="対象ノード"
    )
    content = models.TextField(verbose_name="質問内容")
    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPE_CHOICES,
        verbose_name="質問タイプ"
    )
    depth_level = models.IntegerField(default=1, verbose_name="深掘りレベル")
    context_chunks = models.JSONField(default=list, verbose_name="コンテキストチャンク")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "質問"
        verbose_name_plural = "質問"
        ordering = ['-created_at']
    
    def __str__(self):
        node_title = self.node.title if self.node else "General"
        return f"Question for {node_title} (Level {self.depth_level})"


class Answer(models.Model):
    """回答"""
    question = models.OneToOneField(
        Question, on_delete=models.CASCADE,
        related_name='answer', verbose_name="質問"
    )
    content = models.TextField(verbose_name="回答内容")
    audio_file = models.FileField(
        upload_to='answers/', null=True, blank=True,
        verbose_name="音声ファイル"
    )
    understanding_score = models.FloatField(default=0.0, verbose_name="理解度スコア")
    needs_deeper_questioning = models.BooleanField(default=False, verbose_name="さらなる深掘りが必要")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "回答"
        verbose_name_plural = "回答"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Answer to {self.question.content[:50]}..."


class SessionTimeoutTimer(models.Model):
    """セッションタイムアウトタイマー"""
    session = models.OneToOneField(
        InterviewSession, on_delete=models.CASCADE,
        related_name='timeout_timer', verbose_name="セッション"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name="現在の質問"
    )
    start_time = models.DateTimeField(auto_now_add=True)
    timeout_seconds = models.IntegerField(default=300, verbose_name="タイムアウト秒数")
    is_active = models.BooleanField(default=True, verbose_name="アクティブ")
    
    class Meta:
        verbose_name = "タイムアウトタイマー"
        verbose_name_plural = "タイムアウトタイマー"
    
    def __str__(self):
        return f"Timer for {self.session} ({self.timeout_seconds}s)"
