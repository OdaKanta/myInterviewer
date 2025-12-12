from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from interview_session.models import InterviewSession, Answer, Question
from interview_session.serializers import QuestionSerializer, AnswerSerializer
from .services import QuestionSequenceManager, AnswerEvaluator


@api_view(['POST'])
def generate_next_question(request):
    """次の質問を生成"""
    session_id = request.data.get('session_id')
    
    if not session_id:
        return Response(
            {'error': 'session_idを指定してください。'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        session = InterviewSession.objects.get(id=session_id)
        
        if session.status != 'questioning':
            return Response(
                {'error': '質問フェーズでないセッションです。'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 質問シーケンス管理器を使用
        manager = QuestionSequenceManager()
        
        # 質問を続けるべきかチェック
        if not manager.should_continue_questioning(session):
            session.status = 'completed'
            session.save()
            
            return Response({
                'message': '理解度が十分に達成されました。セッションを完了します。',
                'session_completed': True
            })
        
        # 次の質問を生成
        question = manager.get_next_question(session)
        
        if question:
            serializer = QuestionSerializer(question)
            return Response({
                'question': serializer.data,
                'message': '新しい質問が生成されました。'
            })
        else:
            session.status = 'completed'
            session.save()
            
            return Response({
                'message': 'すべてのトピックが完了しました。',
                'session_completed': True
            })
    
    except InterviewSession.DoesNotExist:
        return Response(
            {'error': '指定されたセッションが見つかりません。'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'質問生成中にエラーが発生しました: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def evaluate_answer(request):
    """回答を評価"""
    answer_id = request.data.get('answer_id')
    
    if not answer_id:
        return Response(
            {'error': 'answer_idを指定してください。'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        answer = Answer.objects.get(id=answer_id)
        
        # 回答を評価
        evaluator = AnswerEvaluator()
        evaluation = evaluator.evaluate_answer(answer)
        
        # 更新された回答データを取得
        updated_answer = Answer.objects.get(id=answer_id)
        answer_serializer = AnswerSerializer(updated_answer)
        
        return Response({
            'evaluation': evaluation,
            'answer': answer_serializer.data,
            'message': '回答の評価が完了しました。'
        })
    
    except Answer.DoesNotExist:
        return Response(
            {'error': '指定された回答が見つかりません。'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'回答評価中にエラーが発生しました: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_session_progress(request):
    """セッションの進捗を取得"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return Response(
            {'error': 'session_idを指定してください。'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        session = InterviewSession.objects.get(id=session_id)
        
        # 全体の進捗を計算
        if session.material.root_node:
            all_nodes = session.material.root_node.get_descendants()
            if all_nodes:
                total_understanding = sum(node.understanding_score for node in all_nodes)
                avg_understanding = total_understanding / len(all_nodes)
                
                # ノード別の進捗
                node_progress = [
                    {
                        'id': node.id,
                        'title': node.title,
                        'understanding_score': node.understanding_score,
                        'questions_count': Question.objects.filter(
                            session=session, node=node
                        ).count(),
                        'answers_count': Answer.objects.filter(
                            question__session=session, question__node=node
                        ).count()
                    }
                    for node in all_nodes
                ]
                
                return Response({
                    'session_id': session.id,
                    'overall_progress': avg_understanding,
                    'total_nodes': len(all_nodes),
                    'completed_nodes': len([n for n in all_nodes if n.understanding_score >= 0.7]),
                    'node_progress': node_progress,
                    'current_node': {
                        'id': session.current_node.id,
                        'title': session.current_node.title
                    } if session.current_node else None
                })
        
        return Response({
            'session_id': session.id,
            'overall_progress': 0.0,
            'total_nodes': 0,
            'completed_nodes': 0,
            'node_progress': [],
            'current_node': None
        })
    
    except InterviewSession.DoesNotExist:
        return Response(
            {'error': '指定されたセッションが見つかりません。'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'進捗取得中にエラーが発生しました: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def skip_current_topic(request):
    """現在のトピックをスキップ"""
    session_id = request.data.get('session_id')
    
    if not session_id:
        return Response(
            {'error': 'session_idを指定してください。'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        session = InterviewSession.objects.get(id=session_id)
        
        if session.status != 'questioning':
            return Response(
                {'error': '質問フェーズでないセッションです。'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 次のトピックに移動
        manager = QuestionSequenceManager()
        question = manager._move_to_next_topic(session)
        
        if question:
            serializer = QuestionSerializer(question)
            return Response({
                'question': serializer.data,
                'message': 'トピックをスキップして次の質問に移りました。'
            })
        else:
            session.status = 'completed'
            session.save()
            
            return Response({
                'message': 'すべてのトピックが完了しました。',
                'session_completed': True
            })
    
    except InterviewSession.DoesNotExist:
        return Response(
            {'error': '指定されたセッションが見つかりません。'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'トピックスキップ中にエラーが発生しました: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
