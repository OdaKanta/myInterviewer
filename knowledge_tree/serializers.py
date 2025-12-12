from rest_framework import serializers
from .models import KnowledgeNode, DocumentChunk, LearningMaterial


class KnowledgeNodeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = KnowledgeNode
        fields = [
            'id', 'title', 'description', 'parent', 'level', 'order', 'children', 'created_at', 'updated_at', 'related_chunks'
        ]
    
    def get_children(self, obj):
        children = obj.children.all().order_by('order')
        return KnowledgeNodeSerializer(children, many=True).data


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = [
            'id', 'content', 'page_number', 'knowledge_nodes', 'created_at'
        ]


class LearningMaterialSerializer(serializers.ModelSerializer):
    root_node = KnowledgeNodeSerializer(read_only=True)
    
    class Meta:
        model = LearningMaterial
        fields = [
            'id', 'title', 'file_path', 'processed', 'root_node',
            'created_at', 'updated_at'
        ]
