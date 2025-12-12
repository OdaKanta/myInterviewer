# このファイルは現在使用されていません
# 現在の実装ではOpenAI Realtime APIを直接使用しており、
# Django ChannelsのWebSocketは使用されていません

# 将来的にWebSocket機能が必要になった場合に備えて、
# コードはコメントアウトして保持します

"""
import json
import base64
import logging
import io
from typing import Dict, Any
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .services import AudioProcessor
import asyncio

logger = logging.getLogger(__name__)


class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.session_group_name = f'interview_{self.session_id}'
        
        await self.channel_layer.group_add(
            self.session_group_name,
            self.channel_name
        )
        # 既存のASGIイベントループを取得（新規作成しない）
        loop = asyncio.get_running_loop()
        # 接続単位のAudioProcessor（内部でRealtimeセッションを確立）
        self.audio_processor = AudioProcessor(loop=loop, language="ja")
        logger.info("✅ InterviewConsumer connected & AudioProcessor ready")
        self.pending_metadata = None  # バイナリデータ待ちのメタデータ
        await self.accept()
        logger.info(f"WebSocket connected for session {self.session_id}")
    
    async def disconnect(self, close_code: int) -> None:
        try:
            # セッションの後始末
            await self.channel_layer.group_discard(
                self.session_group_name,
                self.channel_name
            )
            await database_sync_to_async(self.audio_processor.close)()
        except Exception as e:
            logger.warning(f"close error: {e}")
        logger.info(f"WebSocket disconnected for session {self.session_id}")

    async def receive(self, text_data: str = None, bytes_data: bytes = None) -> None:
        try:
            if text_data:
                # JSONメッセージ処理
                data = json.loads(text_data)
                message_type = data.get('type')
                
                if message_type == 'audio_metadata':
                    # メタデータを保存してバイナリデータを待つ
                    self.pending_metadata = data
                    logger.info(f"📋 Audio metadata received: chunk {data.get('chunk_id')}, size: {data.get('size')}B")
                elif message_type == 'audio_chunk':
                    # 従来のBase64形式
                    await self.handle_audio_chunk(data)
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    
            elif bytes_data:
                # バイナリデータ処理
                if self.pending_metadata:
                    await self.handle_binary_audio_chunk(self.pending_metadata, bytes_data)
                    self.pending_metadata = None
                else:
                    logger.warning("Received binary data without metadata")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    
    
    async def handle_binary_audio_chunk(self, metadata: Dict[str, Any], audio_bytes: bytes) -> None:
        # バイナリ音声チャンクを処理（WAVファイル直接）
        chunk_id = metadata.get('chunk_id', 0)
        audio_format = metadata.get('format', 'unknown')
        expected_size = metadata.get('size', 0)
        
        logger.info(f"🎤 Binary chunk {chunk_id}: format={audio_format}, expected={expected_size}B, actual={len(audio_bytes)}B")
        
        try:
            if audio_bytes and len(audio_bytes) > 0:
                if audio_format == 'wav':
                    # バイナリWAVデータをストリームで処理
                    audio_stream = io.BytesIO(audio_bytes)
                    transcribed_text = await database_sync_to_async(
                        self.audio_processor.transcribe_wav_binary_stream
                    )(audio_stream)
                else:
                    # 他の形式の場合はBase64エンコードして従来処理
                    audio_data = base64.b64encode(audio_bytes).decode('utf-8')
                    transcribed_text = await database_sync_to_async(
                        self.audio_processor.transcribe_audio
                    )(audio_data)
                
                if transcribed_text and transcribed_text.strip():
                    await self.send(text_data=json.dumps({
                        'type': 'transcription_result',
                        'text': transcribed_text.strip(),
                        'is_final': False,
                        'chunk_id': chunk_id
                    }))
                    logger.info(f"✅ Binary transcription: {transcribed_text[:50]}...")
                else:
                    logger.warning(f"⚠️ No transcription result for binary chunk {chunk_id}")
            else:
                logger.warning(f"⚠️ Empty binary data for chunk {chunk_id}")
                    
        except Exception as e:
            logger.error(f"❌ Binary audio processing error for chunk {chunk_id}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'audio_error',
                'message': f'Binary audio processing failed: {str(e)}',
                'chunk_id': chunk_id
            }))

    async def handle_audio_chunk(self, data: Dict[str, Any]) -> None:
        # 音声チャンクを処理（WAVファイル対応）
        audio_data = data.get('audio_data')
        is_final = data.get('is_final', False)
        chunk_id = data.get('chunk_id', 0)
        audio_format = data.get('format', 'unknown')
        
        logger.info(f"🎤 Chunk {chunk_id}: final={is_final}, format={audio_format}, size={len(base64.b64decode(audio_data)) if audio_data else 0}B")
        
        try:
            if audio_data:
                # WAVファイルかどうかをチェック
                if audio_format == 'wav':
                    # WAVファイルは直接OpenAI APIに送信可能
                    transcribed_text = await database_sync_to_async(
                        self.audio_processor.transcribe_wav_direct
                    )(audio_data)
                else:
                    # 従来の処理（Pydub経由）
                    transcribed_text = await database_sync_to_async(
                        self.audio_processor.transcribe_audio
                    )(audio_data)
                
                if transcribed_text and transcribed_text.strip():
                    await self.send(text_data=json.dumps({
                        'type': 'transcription_result',
                        'text': transcribed_text.strip(),
                        'is_final': is_final,
                        'chunk_id': chunk_id
                    }))
                    logger.info(f"✅ Transcription: {transcribed_text[:50]}... (final: {is_final})")
                else:
                    logger.warning(f"⚠️ No transcription result for chunk {chunk_id}")
            else:
                # 音声データがない場合は受信確認のみ
                await self.send(text_data=json.dumps({
                    'type': 'audio_received',
                    'status': 'received',
                    'chunk_id': chunk_id
                }))
                    
        except Exception as e:
            logger.error(f"❌ Audio processing error for chunk {chunk_id}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'audio_error',
                'message': f'Audio processing failed: {str(e)}',
                'chunk_id': chunk_id
            }))
"""
