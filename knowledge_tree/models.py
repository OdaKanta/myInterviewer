from django.db import models
import json


class KnowledgeNode(models.Model):
    """知識ツリーのノード（トピック）"""
    title = models.CharField(max_length=200, verbose_name="ノード名")
    description = models.TextField(verbose_name="説明")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name="親ノード")
    level = models.IntegerField(default=0, verbose_name="階層レベル")
    order = models.IntegerField(default=0, verbose_name="順序")
    related_chunks = models.ManyToManyField('DocumentChunk', related_name='knowledge_nodes', blank=True, verbose_name="関連チャンク")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "知識ノード"
        verbose_name_plural = "知識ノード"
        ordering = ['level', 'order']
    
    def __str__(self):
        return f"{self.title} (Level {self.level})"
    
    def get_descendants(self):
        """子孫ノードをすべて取得"""
        descendants = []
        for child in self.children.all():
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants
    
    def get_ancestors(self):
        """祖先ノードをすべて取得"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors
    
    def get_siblings(self):
        """兄弟ノードをすべて取得"""
        if self.parent is None: # 根ノードは兄弟ノードを持たない
            return self.__class__.objects.none() # 空
        return self.parent.children.exclude(id=self.id) # 親ノードの子ノードのうち、自分自身以外をすべて返す

    # 再帰的に根ノードを取得する関数（現在地のノードから知識ツリーの根のタイトルを参照して LLM プロンプトの中で使う）
    def get_root(self):
        current = self
        while current.parent:
            current = current.parent
        return current


class DocumentChunk(models.Model):
    """PDFから抽出されたチャンク"""
    learning_material = models.ForeignKey('LearningMaterial', on_delete=models.CASCADE, related_name='chunks', verbose_name="学習教材")
    content = models.TextField(verbose_name="内容")
    embedding = models.JSONField(verbose_name="埋め込みベクトル")
    page_number = models.IntegerField(verbose_name="ページ番号")
    chunk_index = models.IntegerField(verbose_name="チャンクID", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "文書チャンク"
        verbose_name_plural = "文書チャンク"
        ordering = ['-learning_material_id', 'page_number']
    
    def __str__(self):
        return f"{self.learning_material.title} - Page {self.page_number} - Chunk {self.chunk_index}"


class LearningMaterial(models.Model):
    """学習教材（PDF）"""
    title = models.CharField(max_length=200, verbose_name="タイトル")
    file_path = models.FileField(upload_to='materials/', verbose_name="ファイル")
    processed = models.BooleanField(default=False, verbose_name="処理済み")
    root_node = models.OneToOneField(KnowledgeNode, on_delete=models.CASCADE, null=True, blank=True, related_name='material', verbose_name="ルートノード")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "学習教材"
        verbose_name_plural = "学習教材"
    
    def __str__(self):
        return self.title
