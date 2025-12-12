from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KnowledgeNodeViewSet, DocumentChunkViewSet

router = DefaultRouter()
router.register(r'nodes', KnowledgeNodeViewSet)
router.register(r'chunks', DocumentChunkViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
