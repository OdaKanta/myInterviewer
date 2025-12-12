from interview_session.models import Question, Answer
from question_engine.services import AnswerEvaluator
from question_engine.services import QuestionSequenceManager
from interview_session.serializers import QuestionSerializer
from interview_session.models import InterviewSession
from rest_framework.decorators import api_view
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from knowledge_tree.models import LearningMaterial
from .models import InterviewSession, Explanation, Question, Answer
from .serializers import (
    InterviewSessionSerializer, ExplanationSerializer,
    QuestionSerializer, AnswerSerializer
)
from .services import ExplanationAnalyzer, SessionManager
from .serializers import QuestionSerializer

import os, requests
import openai
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_502_BAD_GATEWAY
import sys
import json


OPENAI_API_KEY = settings.OPENAI_API_KEY
REALTIME_MODEL = "gpt-4o-mini-transcribe"  # Realtime対応モデル

class InterviewSessionViewSet(viewsets.ModelViewSet):
    queryset = InterviewSession.objects.all()  # デフォルトのqueryset
    serializer_class = InterviewSessionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # 認証されたユーザーのセッションのみ取得
        return InterviewSession.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # 認証されたユーザーでセッションを作成
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"], url_path="realtime/session")
    def create_realtime_session(self, request, pk=None):
        """
        /sessions/{pk}/realtime/session/ (GET)
        -> OpenAI Realtimeのエフェメラル client_secret を返す
        """
        # ここで pk のセッションにアクセス権があるかチェックしておくと安心
        # session = self.get_object()
        # if session.owner != request.user: return Response(status=403)

        try:
            url = "https://api.openai.com/v1/realtime/transcription_sessions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            # payload ={"modalities": ["text"]}
            payload = json.dumps({"input_audio_transcription": {"model": REALTIME_MODEL, "language": "ja"}})

            r = requests.post(
                url,
                headers=headers,
                data=payload,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            print(data)
            return Response({"client_secret": data.get("client_secret")})

        except requests.RequestException as e:
            return Response({"detail": "Failed to create realtime session."})

        except requests.RequestException as e:
            return Response({"detail": "Failed to create realtime session."})

    @action(detail=True, methods=['post'])
    def start_explanation_phase(self, request, pk=None):
        """説明フェーズを開始"""
        session = get_object_or_404(InterviewSession, pk=pk)
        
        if session.status != 'preparing':
            return Response(
                {'error': '説明フェーズを開始できるのは準備中のセッションのみです。'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session.status = 'explaining'
        session.save()
        
        return Response({
            'message': '説明フェーズを開始しました。',
            'session': self.get_serializer(session).data
        })
    
    @action(detail=True, methods=['post'])
    def start_questioning_phase(self, request, pk=None):
        """質問フェーズを開始"""
        session = get_object_or_404(InterviewSession, pk=pk)
        
        if session.status != 'explaining':
            return Response(
                {'error': '質問フェーズを開始できるのは説明フェーズ完了後のみです。'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 次のトピックを選択
        session_manager = SessionManager()
        next_topic = session_manager.select_next_topic(session)
        
        if next_topic:
            session.current_node = next_topic
            session.status = 'questioning'
            session.save()
            
            return Response({
                'message': '質問フェーズを開始しました。',
                'session': self.get_serializer(session).data,
                'current_topic': {
                    'id': next_topic.id,
                    'title': next_topic.title,
                    'description': next_topic.description
                }
            })
        else:
            return Response(
                {'error': '質問対象のトピックが見つかりません。'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def end_session(self, request, pk=None):
        """セッションを終了"""
        session = get_object_or_404(InterviewSession, pk=pk)
        
        session.status = 'completed'
        from django.utils import timezone
        session.ended_at = timezone.now()
        session.save()
        
        return Response({
            'message': 'セッションを終了しました。',
            'session': self.get_serializer(session).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def correct(self, request, pk=None):
        """GPTを使用してテキストを校正"""
        
        session = get_object_or_404(InterviewSession, pk=pk)
        
        text = request.data.get('text', '').strip()
        correction_type = request.data.get('correction_type', 'explanation')
        
        if not text:
            return Response(
                {'success': False, 'error': '校正するテキストが指定されていません。'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            # OpenAI GPT APIを使用してテキストを校正
            import openai
            from django.conf import settings
            
            print("[DEBUG] OK", file=sys.stderr)
            # APIキーの確認
            if not settings.OPENAI_API_KEY:
                return Response(
                    {'success': False, 'error': 'OpenAI APIキーが設定されていません。'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            # 校正タイプに応じてプロンプトを調整
            if correction_type == 'explanation':
                system_prompt = """以下の説明文は学習者が講義内容について振り返ったものです．以下の説明文を以下の観点で校正してください：

1. 元の意味と内容は保持してください
2. 誤字脱字を修正してください
3. 間違った説明を修正してはいけません
4. 出力は校正文章のみ出力すること
"""
            else:
                system_prompt = """あなたは文章校正の専門家です。以下のテキストを文法的に正しく、より読みやすい文章に校正してください。元の意味は保持してください。"""
           
            print("[DEBUG] OK3", file=sys.stderr)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"以下のテキストを校正してください：\n\n{text}"}
                ],
                max_tokens=16000,
                temperature=0.0
            )
            
            print("[DEBUG] OK2", file=sys.stderr)
            corrected_text = response.choices[0].message.content.strip()
            return Response({
                'success': True,
                'corrected_text': corrected_text,
                'original_text': text
            })
            
        except openai.BadRequestError as e:
            print(f"OpenAI BadRequestError: {e}")
            return Response(
                {'success': False, 'error': f'OpenAI APIリクエストエラー: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except openai.AuthenticationError as e:
            print(f"OpenAI AuthenticationError: {e}")
            return Response(
                {'success': False, 'error': 'OpenAI API認証エラー: APIキーを確認してください。'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except openai.RateLimitError as e:
            print(f"OpenAI RateLimitError: {e}")
            return Response(
                {'success': False, 'error': 'OpenAI APIレート制限に達しました。しばらく待ってから再試行してください。'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        except Exception as e:
            print(f"General error: {e}")
            return Response(
                {'success': False, 'error': f'校正処理中にエラーが発生しました: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ExplanationViewSet(viewsets.ModelViewSet):
    queryset = Explanation.objects.all()
    serializer_class = ExplanationSerializer
    
    def create(self, request):
        """説明を作成"""
        session_id = request.data.get('session_id')
        content = request.data.get('content')
        
        try:
            session = InterviewSession.objects.get(id=session_id)
            
            # 説明を分析
            analyzer = ExplanationAnalyzer()
            topics = analyzer.analyze_explanation(content, session.material)
            
            # 説明レコードを作成
            explanation = analyzer.create_explanation_record(
                session, content, topics
            )
            
            return Response({
                'message': '説明が保存されました。',
                'explanation': self.get_serializer(explanation).data,
                'topics': topics
            })
            
        except InterviewSession.DoesNotExist:
            return Response(
                {'error': '指定されたセッションが見つかりません。'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'説明の処理中にエラーが発生しました: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class QuestionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    
    @action(detail=False, methods=['get'])
    def by_session(self, request):
        """セッションの質問一覧を取得"""
        session_id = request.query_params.get('session_id')
        
        if session_id:
            questions = Question.objects.filter(session_id=session_id)
            serializer = self.get_serializer(questions, many=True)
            return Response(serializer.data)
        
        return Response(
            {'error': 'session_idを指定してください。'},
            status=status.HTTP_400_BAD_REQUEST
        )


class AnswerViewSet(viewsets.ModelViewSet):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer
    
    def create(self, request):
        """回答を作成"""
        session_id = request.data.get('session_id')
        question_id = request.data.get('question_id')
        content = request.data.get('content')
        
        try:
            # 質問またはセッションから情報を取得
            if question_id:
                question = Question.objects.get(id=question_id)
                session = question.session
            elif session_id:
                session = InterviewSession.objects.get(id=session_id)
                # 最新の質問を取得
                question = Question.objects.filter(session=session).order_by('-created_at').first()
                if not question:
                    return Response(
                        {'error': '質問が見つかりません。'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                return Response(
                    {'error': 'session_id または question_id を指定してください。'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 回答を保存
            answer = Answer.objects.create(
                question=question,
                content=content
            )
            
            # 次の質問を生成
            next_question = self._generate_next_question(session, answer)
            
            response_data = {
                'message': '回答が保存されました。',
                'answer': self.get_serializer(answer).data
            }
            
            if next_question:
                response_data['next_question'] = {
                    'id': next_question.id,
                    'content': next_question.content
                }
            
            return Response(response_data)
            
        except Question.DoesNotExist:
            return Response(
                {'error': '指定された質問が見つかりません。'},
                status=status.HTTP_404_NOT_FOUND
            )
        except InterviewSession.DoesNotExist:
            return Response(
                {'error': '指定されたセッションが見つかりません。'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'回答の処理中にエラーが発生しました: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _generate_next_question(self, session, previous_answer):
        """前の回答に基づいて次の質問を生成"""
        try:
            # 既に回答済みの質問数をチェック
            answered_questions = Question.objects.filter(
                session=session, 
                answer__isnull=False
            ).count()
            
            # 最大質問数に達した場合は終了
            MAX_QUESTIONS = 3
            if answered_questions >= MAX_QUESTIONS:
                return None
            
            # GPTを使用して次の質問を生成
            import openai
            from django.conf import settings
            
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            # 説明文を取得
            explanation = Explanation.objects.filter(session=session).first()
            
            # これまでの質問と回答の履歴を取得
            qa_history = []
            for q in Question.objects.filter(session=session).order_by('created_at'):
                if hasattr(q, 'answer'):
                    qa_history.append(f"質問: {q.content}\n回答: {q.answer.content}")
            
            history_text = "\n\n".join(qa_history) if qa_history else "なし"
            
            system_prompt = """あなたは教育的なAI面接官です。学習者の説明と前回の回答を受けて、さらに理解を深めるための質問を行います。

以下の点に注意して質問を生成してください：
1. 前回の回答を踏まえた発展的な質問
2. より具体的な理解を確認する質問
3. 実際の応用や関連する概念について問う質問
4. 1つの明確で答えやすい質問にしてください
5. 日本語で出力してください
6. 前回と同じような質問は避けてください"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"""学習者の説明：
{explanation.content if explanation else "なし"}

これまでの質問と回答の履歴：
{history_text}

前回の回答：{previous_answer.content}

上記を踏まえて、理解をさらに深めるための次の質問を1つ生成してください。"""}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            question_content = response.choices[0].message.content.strip()
            
            # 質問をデータベースに保存
            question = Question.objects.create(
                session=session,
                content=question_content,
                question_type='follow_up'
            )
            
            return question
            
        except Exception as e:
            print(f"Next question generation error: {e}")
            return None

@api_view(['POST'])
def create_answer(request):
    """
    回答を保存し、question_engine で評価＆次の質問を生成して返す
    リクエストJSON: { "session_id": 1, "question_id": 2, "content": "..." }
    """
    session_id = request.data.get('session_id')
    question_id = request.data.get('question_id')
    content = request.data.get('content', '').strip()

    if not session_id or not question_id or not content:
        return Response({'error': 'session_id, question_id, content は必須です。'},
                        status=status.HTTP_400_BAD_REQUEST)

    session = get_object_or_404(InterviewSession, id=session_id)
    question = get_object_or_404(Question, id=question_id, session=session)

    # 1) 回答を保存
    answer = Answer.objects.create(
        question=question,
        content=content
    )

    # 2) 回答の評価（理解度スコアなど）→ ノードの理解度更新
    evaluator = AnswerEvaluator()
    evaluation = evaluator.evaluate_answer(answer)   # ← ノード理解度は平均で更新されます :contentReference[oaicite:18]{index=18}

    # 3) 次の質問を生成
    manager = QuestionSequenceManager()
    next_q = manager.get_next_question(session)

    resp = {
        'answer': {
            'id': answer.id,
            'content': answer.content,
            'evaluation': evaluation
        }
    }

    if next_q:
        serializer = QuestionSerializer(next_q)
        resp['next_question'] = serializer.data
    else:
        # もう質問がなければ、フロントは“終了推奨”表示にできます
        resp['next_question'] = None
        resp['session_completed'] = True

    return Response(resp, status=status.HTTP_200_OK)