from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from knowledge_tree.models import LearningMaterial
from interview_session.models import InterviewSession
from knowledge_tree.services import MaterialProcessor
from .decorators import material_manager_required, check_material_manager_permission

from django.conf import settings

@login_required
def home(request):
    """ホームページ"""
    materials = LearningMaterial.objects.all().order_by('-created_at')
    
    if request.user.is_authenticated:
        # ログインユーザーのセッションのみ表示
        sessions = InterviewSession.objects.filter(user=request.user).order_by('-started_at')[:5]
    else:
        sessions = []

    context = {
        'materials': materials,
        'recent_sessions': sessions,
        'is_material_manager': check_material_manager_permission(request.user)
    }
    return render(request, 'frontend/home.html', context)


@material_manager_required #「このページを使えるのは教材管理者だけだよ」という制限
def upload_material(request):
    """教材アップロードページ（教材管理者のみ）"""
    if request.method == 'POST': # ユーザーがフォームを送信したときだけ、この中の処理を行う
        title = request.POST.get('title')
        file = request.FILES.get('file') # パス名ではなくファイルそのものを取得
        
        if title and file:
            try:
                # 教材を作成
                material = LearningMaterial.objects.create(title=title, file_path=file)
                
                # Celeryタスクでバックグラウンド処理（時間がかかる処理を裏側（バックグラウンド）で行う）
                MaterialProcessor.start_processing_workflow.delay(material.id)
                
                messages.success(request, f'教材「{title}」がアップロードされました。処理はバックグラウンドで実行中です。')
                return redirect('dashboard')
                
            except Exception as e:
                messages.error(request, f'教材の処理中にエラーが発生しました: {str(e)}')
        else:
            messages.error(request, 'タイトルとファイルを指定してください。')
    
    return render(request, 'frontend/upload.html')


@login_required
def interview(request, session_id):
    """インタビューページ（レガシー - 説明フェーズにリダイレクト）"""
    session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
    
    # セッションが新規の場合は説明フェーズを開始
    if session.status == 'preparing':
        session.status = 'explaining'
        session.save()
    
    # 説明フェーズにリダイレクト
    return redirect('explanation_phase', session_id=session_id)


@login_required
def explanation_phase(request, session_id):
    """説明フェーズページ"""
    session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
    
    # セッションが新規の場合は説明フェーズを開始
    if session.status == 'preparing':
        session.status = 'explaining'
        session.save()
    
    # 説明フェーズ以外の場合は適切なページにリダイレクト
    if session.status == 'questioning':
        return redirect('questioning_phase', session_id=session_id)
    elif session.status == 'completed':
        messages.info(request, 'このセッションは既に完了しています。')
        return redirect('dashboard')
    
    context = {
        'session': session,
        'material': session.material,
        'knowledge_tree': session.material.root_node if session.material.processed else None
    }
    
    return render(request, 'frontend/explanation_phase.html', context)


@login_required
def questioning_phase(request, session_id):
    """深堀フェーズ（質問フェーズ）ページ"""
    session = get_object_or_404(InterviewSession, id=session_id, user=request.user)
    
    # 質問フェーズ以外の場合は適切なページにリダイレクト
    if session.status == 'explaining':
        messages.warning(request, '説明フェーズを完了してから深堀フェーズに進んでください。')
        return redirect('explanation_phase', session_id=session_id)
    elif session.status == 'preparing':
        messages.warning(request, 'セッションの準備が完了していません。')
        return redirect('explanation_phase', session_id=session_id)
    elif session.status == 'completed':
        messages.info(request, 'このセッションは既に完了しています。')
        return redirect('dashboard')
    
    context = {
        'session': session,
        'material': session.material,
        'knowledge_tree': session.material.root_node if session.material.processed else None
    }
    
    return render(request, 'frontend/questioning_phase.html', context)


@login_required
def knowledge_tree_visualization(request, material_id):
    """知識ツリー可視化ページ"""
    material = get_object_or_404(LearningMaterial, id=material_id)
    
    if not material.processed:
        messages.warning(request, 'この教材はまだ処理されていません。')
        return redirect('dashboard')
    
    context = {
        'material': material,
        'knowledge_tree': material.root_node
    }
    
    return render(request, 'frontend/knowledge_tree.html', context)
