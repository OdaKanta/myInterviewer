from django.urls import path
from . import views, auth_views

urlpatterns = [
    # トップページはログインページ
    path('', auth_views.login_view, name='home'),
    
    # 認証関連
    path('login/', auth_views.login_view, name='login'),
    path('register/', auth_views.register_view, name='register'),
    path('logout/', auth_views.logout_view, name='logout'),
    path('profile/', auth_views.profile_view, name='profile'),
    
    # メインダッシュボード（ログイン後のホーム）
    path('dashboard/', views.home, name='dashboard'),
    
    # インタビュー関連
    path('interview/<int:session_id>/', views.interview, name='interview'),  # レガシー
    path('interview/<int:session_id>/explanation/', views.explanation_phase, name='explanation_phase'),
    path('interview/<int:session_id>/questioning/', views.questioning_phase, name='questioning_phase'),
    
    # その他
    path('upload/', views.upload_material, name='upload_material'),
    path('tree/<int:material_id>/', views.knowledge_tree_visualization, name='knowledge_tree_visualization'),
]
