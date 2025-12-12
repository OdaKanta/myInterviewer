import json
import asyncio
import base64
import logging
from typing import Dict, Any, Optional
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import InterviewSession, Question, Answer
from .services import AudioProcessor, ExplanationAnalyzer

# ログ設定
logger = logging.getLogger(__name__)


class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.session_group_name = f'interview_{self.session_id}'
        
        # Join session group
        await self.channel_layer.group_add(
            self.session_group_name,
            self.channel_name
        )
        
        # AudioProcessorを初期化
        self.audio_processor = AudioProcessor()
        
        # Realtime API転写コールバックを設定
        async def transcription_callback(data):
            await self.handle_realtime_transcription(data)
        
        # Realtime Transcriberを初期化（非同期）
        try:
            success = await self.audio_processor.initialize_realtime_transcriber(transcription_callback)
            if success:
                print("Realtime transcription enabled for session")
            else:
                print("Falling back to standard transcription")
        except Exception as e:
            print(f"Realtime transcriber initialization failed: {e}")
        
        await self.accept()
    
    async def disconnect(self, close_code: int) -> None:
        """WebSocket切断処理"""
        # Realtime transcriberをクリーンアップ
        if hasattr(self, 'audio_processor') and self.audio_processor.realtime_transcriber:
            try:
                await self.audio_processor.realtime_transcriber.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting realtime transcriber: {e}")
        
        # セッショングループから離脱
        await self.channel_layer.group_discard(
            self.session_group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def handle_realtime_transcription(self, data: Dict[str, Any]) -> None:
        """Realtime API からの転写結果を処理"""
        message_type = data.get("type")
        
        response_map = {
            "transcription_partial": {
                'type': 'streaming_transcription',
                'text': data.get('text', ''),
                'is_partial': True
            },
            "transcription_completed": {
                'type': 'transcription_result',
                'text': data.get('text', ''),
                'is_final': True,
                'is_partial': False
            },
            "speech_started": {
                'type': 'speech_detected',
                'status': 'started'
            },
            "speech_stopped": {
                'type': 'speech_detected',
                'status': 'stopped'
            },
            "error": {
                'type': 'audio_error',
                'message': f"Realtime API error: {data.get('error', {}).get('message', 'Unknown error')}"
            }
        }
        
        if message_type in response_map:
            await self.send(text_data=json.dumps(response_map[message_type]))
        else:
            logger.warning(f"Unknown realtime transcription message type: {message_type}")
    
    async def receive(self, text_data: str) -> None:
        """WebSocketメッセージ受信処理"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # メッセージタイプに応じて処理を分岐
            handler_map = {
                'audio_chunk': self.handle_audio_chunk,
                'text_input': self.handle_text_input,
                'session_control': self.handle_session_control
            }
            
            if message_type in handler_map:
                await handler_map[message_type](data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Message processing failed'
            }))
    
    async def handle_audio_chunk(self, data: Dict[str, Any]) -> None:
        """音声チャンクを処理（シンプル版）"""
        audio_data = data.get('audio_data')
        is_final = data.get('is_final', False)
        chunk_id = data.get('chunk_id', 0)
        
        logger.info(f"🎤 Audio chunk {chunk_id}: final={is_final}, size={len(base64.b64decode(audio_data)) if audio_data else 0}B")
        
        if not hasattr(self, 'audio_processor'):
            self.audio_processor = AudioProcessor()
        
        try:
            if is_final and audio_data:
                # 最終チャンクのみ処理
                transcribed_text = await database_sync_to_async(
                    self.audio_processor.transcribe_audio
                )(audio_data)
                
                if transcribed_text and transcribed_text.strip():
                    await self.send(text_data=json.dumps({
                        'type': 'transcription_result',
                        'text': transcribed_text.strip(),
                        'is_final': True,
                        'chunk_id': chunk_id
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'audio_error',
                        'message': 'No transcription result'
                    }))
            else:
                # 中間チャンクは受信確認のみ
                await self.send(text_data=json.dumps({
                    'type': 'audio_received',
                    'status': 'received',
                    'chunk_id': chunk_id
                }))
                    
        except Exception as e:
            logger.error(f"Audio processing error for chunk {chunk_id}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'audio_error',
                'message': f'Audio processing failed: {str(e)}',
                'chunk_id': chunk_id
            }))

    async def _handle_streaming_chunk(self, audio_data: str, chunk_id: int, processing_hint: str, chunk_type: str) -> None:
        """ストリーミング音声チャンクの処理"""
        is_pydub_preferred = processing_hint == 'pydub_preferred' or chunk_type == 'streaming_pydub'
        
        # Realtime transcriberを初期化（初回のみ）
        await self._ensure_realtime_transcriber()
        
        if self._is_realtime_available():
            # Realtime API使用
            result = await self.audio_processor.process_realtime_audio_chunk_v2(
                audio_data, 
                self.audio_processor.realtime_transcriber
            )
            status = 'pydub_realtime_processing' if is_pydub_preferred else 'realtime_processing'
            await self._send_audio_received(chunk_id, status if result == "PROCESSING" else status.replace('processing', 'waiting'))
        else:
            # フォールバック処理
            result = self.audio_processor.process_audio_chunk_streaming(audio_data)
            if result and result.strip():
                await self._send_transcription_result(result.strip(), True, chunk_id, 'fallback')
            else:
                status = 'pydub_fallback_buffering' if is_pydub_preferred else 'fallback_buffering'
                await self._send_audio_received(chunk_id, status)

    async def _handle_final_chunk(self, audio_data: str, chunk_id: int, processing_hint: str, audio_format: str) -> None:
        """最終音声チャンクの処理"""
        is_pydub_preferred = processing_hint == 'pydub_preferred'
        
        logger.info(f"Processing final chunk {chunk_id}, Pydub preferred: {is_pydub_preferred}, format: {audio_format}")
        
        if self._is_realtime_available():
            # Realtime APIでコミット
            await self.audio_processor.commit_realtime_audio()
            method = 'pydub_realtime' if is_pydub_preferred else 'realtime'
            await self._send_audio_received(chunk_id, f'{method}_final_committed', method)
        else:
            # 従来の転写方式
            transcribed_text = await database_sync_to_async(
                self.audio_processor.transcribe_audio
            )(audio_data)
            
            if transcribed_text and transcribed_text.strip():
                method = 'pydub_fallback' if is_pydub_preferred else 'fallback'
                await self._send_transcription_result(transcribed_text.strip(), False, chunk_id, method)
            else:
                error_msg = 'Pydub transcription failed' if is_pydub_preferred else 'Transcription failed'
                await self._send_error_response(chunk_id, error_msg)

    async def _ensure_realtime_transcriber(self) -> None:
        """Realtime transcriberの初期化を確保"""
        if not hasattr(self.audio_processor, 'realtime_transcriber') or not self.audio_processor.realtime_transcriber:
            await self.audio_processor.initialize_realtime_transcriber(self.handle_realtime_transcription)

    def _is_realtime_available(self) -> bool:
        """Realtime APIが利用可能かチェック"""
        return (hasattr(self.audio_processor, 'realtime_transcriber') and 
                self.audio_processor.realtime_transcriber and 
                self.audio_processor.realtime_transcriber.is_connected)

    async def _send_transcription_result(self, text: str, is_partial: bool, chunk_id: int, method: str) -> None:
        """転写結果を送信"""
        await self.send(text_data=json.dumps({
            'type': 'streaming_transcription' if is_partial else 'transcription_result',
            'text': text,
            'is_partial': is_partial,
            'is_final': not is_partial,
            'chunk_id': chunk_id,
            'processing_method': method
        }))

    async def _send_audio_received(self, chunk_id: int, status: str, method: Optional[str] = None) -> None:
        """音声受信確認を送信"""
        response = {
            'type': 'audio_received',
            'status': status,
            'chunk_id': chunk_id
        }
        if method:
            response['processing_method'] = method
        await self.send(text_data=json.dumps(response))

    async def _send_error_response(self, chunk_id: int, message: str) -> None:
        """エラーレスポンスを送信"""
        await self.send(text_data=json.dumps({
            'type': 'audio_error',
            'message': message,
            'chunk_id': chunk_id
        }))
    
    async def handle_text_input(self, data):
        """テキスト入力を処理"""
        text = data.get('text')
        input_type = data.get('input_type')  # 'explanation' or 'answer'
        
        if input_type == 'explanation':
            await self.process_explanation(text)
        elif input_type == 'answer':
            await self.process_answer(text, data.get('question_id'))
    
    async def process_explanation(self, text):
        """説明を処理してトピックを抽出"""
        session = await database_sync_to_async(
            InterviewSession.objects.get
        )(id=self.session_id)
        
        # 説明を分析してトピックを抽出
        analyzer = ExplanationAnalyzer()
        topics = await database_sync_to_async(
            analyzer.analyze_explanation
        )(text, session.material)
        
        # クライアントにトピック抽出結果を送信
        await self.send(text_data=json.dumps({
            'type': 'topics_extracted',
            'topics': topics
        }))
    
    async def process_answer(self, text, question_id):
        """回答を処理"""
        # 回答を保存
        answer = await database_sync_to_async(
            self.save_answer
        )(question_id, text)
        
        # 理解度を評価
        from question_engine.services import AnswerEvaluator
        evaluator = AnswerEvaluator()
        evaluation = await database_sync_to_async(
            evaluator.evaluate_answer
        )(answer)
        
        # クライアントに評価結果を送信
        await self.send(text_data=json.dumps({
            'type': 'answer_evaluated',
            'evaluation': evaluation,
            'needs_deeper_questioning': evaluation.get('needs_deeper_questioning', False)
        }))
    
    def save_answer(self, question_id, text):
        """回答を保存"""
        question = Question.objects.get(id=question_id)
        answer = Answer.objects.create(
            question=question,
            content=text
        )
        return answer
    
    async def handle_session_control(self, data):
        """セッション制御"""
        action = data.get('action')
        
        if action == 'start_questioning':
            await self.start_questioning_phase()
        elif action == 'pause_session':
            await self.pause_session()
        elif action == 'end_session':
            await self.end_session()
    
    async def start_questioning_phase(self):
        """質問フェーズを開始"""
        session = await database_sync_to_async(
            InterviewSession.objects.get
        )(id=self.session_id)
        
        session.status = 'questioning'
        await database_sync_to_async(session.save)()
        
        await self.send(text_data=json.dumps({
            'type': 'phase_changed',
            'phase': 'questioning'
        }))
    
    async def pause_session(self):
        """セッションを一時停止"""
        session = await database_sync_to_async(
            InterviewSession.objects.get
        )(id=self.session_id)
        
        session.status = 'paused'
        await database_sync_to_async(session.save)()
        
        await self.send(text_data=json.dumps({
            'type': 'session_paused'
        }))
    
    async def end_session(self):
        """セッションを終了"""
        session = await database_sync_to_async(
            InterviewSession.objects.get
        )(id=self.session_id)
        
        session.status = 'completed'
        await database_sync_to_async(session.save)()
        
        await self.send(text_data=json.dumps({
            'type': 'session_ended'
        }))
    
    # Group message handlers
    async def new_question(self, event):
        """新しい質問をクライアントに送信"""
        await self.send(text_data=json.dumps({
            'type': 'new_question',
            'question': event['question']
        }))
    
    async def timeout_warning(self, event):
        """タイムアウト警告をクライアントに送信"""
        await self.send(text_data=json.dumps({
            'type': 'timeout_warning',
            'remaining_seconds': event['remaining_seconds']
        }))
