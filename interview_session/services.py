import io
import base64
import wave
import json
import asyncio
import websockets
from openai import OpenAI
from django.conf import settings
from django.core.files.base import ContentFile
from sentence_transformers import SentenceTransformer
from knowledge_tree.models import KnowledgeNode, DocumentChunk
from .models import Explanation


# AudioProcessorクラスは現在使用されていません
# 現在の実装ではフロントエンドでOpenAI Realtime APIを直接使用しており、
# サーバーサイドでの音声処理は行われていません

# 将来的にサーバーサイド音声処理が必要になった場合に備えて保持

"""
class AudioProcessor:
    # 音声処理クラス - 現在未使用
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.audio_buffer = []
        self.is_speaking = False
        
    def add_audio_chunk(self, audio_data):
        # 音声チャンクをバッファに追加
        try:
            audio_bytes = base64.b64decode(audio_data)
            self.audio_buffer.append(audio_bytes)
            self.is_speaking = True
            return True
        except Exception as e:
            print(f"Audio chunk processing error: {e}")
            return False
    
    def process_audio_buffer(self):
        # バッファされた音声データを処理
        if not self.audio_buffer:
            return ""
        
        try:
            # バッファを結合
            combined_audio = b''.join(self.audio_buffer)
            
            # 音声ファイルを作成
            audio_file = io.BytesIO(combined_audio)
            audio_file.name = "audio.wav"
            
            # Whisper APIで転写（ストリーミングサポートの場合）
            transcript = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ja",
                response_format="text"  # より高速な応答のためテキスト形式を指定
            )
            
            # バッファをクリア
            self.audio_buffer = []
            self.is_speaking = False
            
            return transcript if isinstance(transcript, str) else transcript.text
            
        except Exception as e:
            print(f"Audio transcription error: {e}")
            self.audio_buffer = []
            return ""
    
    # ... その他のメソッドもコメントアウト ...
"""


class ExplanationAnalyzer:
    """説明分析クラス"""
    
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def analyze_explanation(self, explanation_text, material):
        """説明を分析してトピックを抽出"""
        try:
            print(f"Analyzing explanation for material: {material.id}")
            
            # 当該教材の知識ツリーのノードを取得
            if not material.root_node:
                return []
            
            # ルートノードの子孫ノードのみを取得（ルート自体は除外）
            nodes = material.root_node.get_descendants().values_list(
                'id', 'title', 'description'
            )
            
            # ノード情報を文字列に変換
            node_info = "\n".join([
                f"ID: {node[0]}, タイトル: {node[1]}, 説明: {node[2]}"
                for node in nodes
            ])
            
            # LLMでトピック抽出
            prompt = f"""
            以下の学習者の説明から、言及されているトピックを特定してください。
            
            学習者の説明:
            {explanation_text}
            
            利用可能なトピック:
            {node_info}
            
            言及されているトピックのIDをJSON配列で返してください。
            例: [1, 3, 5]
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは学習内容の分析専門家です。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            # 結果を解析
            import json
            topic_ids = json.loads(response.choices[0].message.content)
            
            # トピック情報を取得
            topics = []
            for topic_id in topic_ids:
                try:
                    node = KnowledgeNode.objects.get(id=topic_id)
                    topics.append({
                        'id': node.id,
                        'title': node.title,
                        'description': node.description,
                        'understanding_score': node.understanding_score
                    })
                except KnowledgeNode.DoesNotExist:
                    continue
            
            return topics
            
        except Exception as e:
            print(f"Explanation analysis error: {e}")
            return []
    
    def create_explanation_record(self, session, content, topics, audio_file=None):
        """説明レコードを作成"""
        explanation = Explanation.objects.create(
            session=session,
            content=content,
            audio_file=audio_file
        )
        
        # トピックを関連付け
        for topic_data in topics:
            try:
                node = KnowledgeNode.objects.get(id=topic_data['id'])
                explanation.topics_mentioned.add(node)
            except KnowledgeNode.DoesNotExist:
                continue
        
        return explanation


class SessionManager:
    """セッション管理クラス"""
    
    def select_next_topic(self, session):
        """次の質問対象トピックを選択"""
        # 理解度が低いトピックを優先
        if session.material.root_node:
            # 子ノードから理解度が最も低いものを選択
            candidates = KnowledgeNode.objects.filter(
                parent=session.material.root_node
            ).order_by('understanding_score')
            
            if candidates.exists():
                return candidates.first()
        
        return None
    
    def update_node_understanding(self, node, score_delta):
        """ノードの理解度を更新"""
        new_score = max(0, min(1, node.understanding_score + score_delta))
        node.understanding_score = new_score
        node.save()
        
        # 親ノードの理解度も更新
        if node.parent:
            children = node.parent.children.all()
            avg_score = sum(child.understanding_score for child in children) / len(children)
            node.parent.understanding_score = avg_score
            node.parent.save()


class TimeoutManager:
    """タイムアウト管理クラス"""
    
    def __init__(self, session):
        self.session = session
    
    def start_timer(self, question, timeout_seconds=300):
        """タイマーを開始"""
        from .models import SessionTimeoutTimer
        
        timer, created = SessionTimeoutTimer.objects.get_or_create(
            session=self.session,
            defaults={
                'question': question,
                'timeout_seconds': timeout_seconds,
                'is_active': True
            }
        )
        
        if not created:
            timer.question = question
            timer.timeout_seconds = timeout_seconds
            timer.is_active = True
            timer.save()
        
        return timer
    
    def stop_timer(self):
        """タイマーを停止"""
        try:
            timer = self.session.timeout_timer
            timer.is_active = False
            timer.save()
        except:
            pass
