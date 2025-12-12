from django.contrib import admin
from .models import LearningMaterial, KnowledgeNode, DocumentChunk


@admin.register(LearningMaterial)
class LearningMaterialAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'processed', 'created_at']
    list_filter = ['processed', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'level', 'order', 'parent']
    list_filter = ['level', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['level', 'order']


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ['id', 'learning_material', 'learning_material_id', 'page_number', 'chunk_index', 'created_at']
    list_filter = ['page_number', 'created_at']
    readonly_fields = ['created_at']
