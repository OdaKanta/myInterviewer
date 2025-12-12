import asyncio
import json
import base64
import websockets
import logging
import io
import wave
import audioop
from typing import AsyncGenerator, Optional, Callable
from django.conf import settings
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class PCMConverter:
    """WebMオーディオをPCM16に変換するクラス"""
    
    @staticmethod
    def webm_to_pcm16(webm_data: bytes, sample_rate: int = 16000) -> bytes:
        """WebMデータをPCM16形式に変換（複数フォーマット対応）"""
        try:
            print(f"🔄 [PCM CONVERTER] Converting {len(webm_data)} bytes to PCM16")
            
            # 最初にWebMとして処理を試行
            formats_tried = []
            audio = None
            
            try:
                audio = AudioSegment.from_file(io.BytesIO(webm_data), format="webm")
                print(f"✅ [PCM CONVERTER] Decoded as WebM")
            except Exception as e:
                formats_tried.append(f"webm: {e}")
                # WebMが失敗した場合、他のフォーマットを試行
                try:
                    audio = AudioSegment.from_file(io.BytesIO(webm_data), format="ogg")
                    print(f"✅ [PCM CONVERTER] Decoded as OGG")
                except Exception as e2:
                    formats_tried.append(f"ogg: {e2}")
                    try:
                        audio = AudioSegment.from_file(io.BytesIO(webm_data), format="mp4")
                        print(f"✅ [PCM CONVERTER] Decoded as MP4")
                    except Exception as e3:
                        formats_tried.append(f"mp4: {e3}")
                        # 最後の手段：フォーマットを自動検出
                        audio = AudioSegment.from_file(io.BytesIO(webm_data))
                        print(f"✅ [PCM CONVERTER] Decoded with auto-detection")
            
            print(f"📊 [PCM CONVERTER] Original: {audio.frame_rate}Hz, {audio.channels}ch, {len(audio)}ms")
            
            # 16kHz, mono, 16-bitに変換
            audio = audio.set_frame_rate(sample_rate)
            audio = audio.set_channels(1)
            audio = audio.set_sample_width(2)  # 16-bit
            
            # raw PCMデータを取得
            pcm_data = audio.raw_data
            
            print(f"✅ [PCM CONVERTER] PCM16 output: {len(pcm_data)} bytes ({sample_rate}Hz, mono, 16-bit)")
            return pcm_data
            
        except Exception as e:
            print(f"❌ [PCM CONVERTER] Conversion failed: {e}")
            if formats_tried:
                print(f"    Attempted formats: {formats_tried}")
            logger.error(f"Failed to convert audio to PCM16: {e}")
            return b""
    
    @staticmethod
    def wav_to_pcm16(wav_data: bytes, sample_rate: int = 16000) -> bytes:
        """WAVデータをPCM16形式に変換"""
        try:
            # WAVファイルを読み込み
            with wave.open(io.BytesIO(wav_data), 'rb') as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                
                # サンプルレート変換
                if wav_file.getframerate() != sample_rate:
                    frames = audioop.ratecv(
                        frames, 
                        wav_file.getsampwidth(), 
                        wav_file.getnchannels(),
                        wav_file.getframerate(), 
                        sample_rate, 
                        None
                    )[0]
                
                # モノラル変換
                if wav_file.getnchannels() == 2:
                    frames = audioop.tomono(frames, wav_file.getsampwidth(), 1, 1)
                
                # 16-bit変換
                if wav_file.getsampwidth() != 2:
                    frames = audioop.lin2lin(frames, wav_file.getsampwidth(), 2)
                
                logger.debug(f"Converted WAV to PCM16: {len(frames)} bytes")
                return frames
                
        except Exception as e:
            logger.error(f"Failed to convert WAV to PCM16: {e}")
            return b""



class RealtimeTranscriber:
    """OpenAI Realtime APIを使用したリアルタイム音声転写クラス"""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.api_key = settings.OPENAI_API_KEY
        self.websocket = None
        self.is_connected = False
        self.callback = callback  # 転写結果を受け取るコールバック関数
        self.session_id = None
        
    async def connect(self):
        """OpenAI Realtime APIに接続（転写専用モード）"""
        try:
            # OpenAI Realtime API エンドポイント（転写専用）
            uri = "wss://api.openai.com/v1/realtime?intent=transcription"
            
            # 認証ヘッダー
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            # WebSocket接続
            try:
                # 新しいwebsocketsライブラリの場合
                self.websocket = await websockets.connect(
                    uri,
                    additional_headers=headers,
                    timeout=10
                )
            except TypeError:
                # 古いバージョンの場合
                self.websocket = await websockets.connect(
                    uri,
                    extra_headers=headers,
                    timeout=10
                )
            
            self.is_connected = True
            logger.info("Connected to OpenAI Realtime API (transcription mode)")
            
            # 転写専用セッションを設定
            await self._configure_transcription_session()
            
            # メッセージリスナーを開始
            asyncio.create_task(self._listen_for_messages())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            self.is_connected = False
            return False
    
    async def _configure_transcription_session(self):
        """転写専用セッション設定"""
        try:
            # 参考コードに基づく転写専用設定
            config = {
                "type": "transcription_session.update",
                "session": {
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                    }
                }
            }
            
            await self.websocket.send(json.dumps(config))
            logger.info("Transcription session configuration sent")
            
        except Exception as e:
            logger.error(f"Failed to configure transcription session: {e}")
            self.is_connected = False
    
    async def _listen_for_messages(self):
        """OpenAI からのメッセージを監視"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection to OpenAI closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error in message listener: {e}")
            self.is_connected = False
    
    async def _handle_message(self, data):
        """OpenAIからのメッセージを処理（転写専用）"""
        message_type = data.get("type")
        
        if message_type == "session.created":
            self.session_id = data.get("session", {}).get("id")
            logger.info(f"Transcription session created: {self.session_id}")
            
        elif message_type == "conversation.item.input_audio_transcription.delta":
            # 部分転写結果（リアルタイム）
            delta_text = data.get("delta", "")
            if delta_text and self.callback:
                await self.callback({
                    "type": "transcription_partial",
                    "text": delta_text,
                    "is_partial": True
                })
                
        elif message_type == "conversation.item.input_audio_transcription.completed":
            # 転写完了
            transcript = data.get("transcript", "")
            if transcript and self.callback:
                await self.callback({
                    "type": "transcription_completed",
                    "text": transcript,
                    "is_final": True
                })
                
        elif message_type == "input_audio_buffer.speech_started":
            # 音声検出開始
            if self.callback:
                await self.callback({
                    "type": "speech_started"
                })
                
        elif message_type == "input_audio_buffer.speech_stopped":
            # 音声検出停止
            if self.callback:
                await self.callback({
                    "type": "speech_stopped"
                })
                
        elif message_type == "error":
            # エラー処理
            error = data.get("error", {})
            logger.error(f"OpenAI Realtime API error: {error}")
            if self.callback:
                await self.callback({
                    "type": "error",
                    "error": error
                })
        
        # デバッグ用：その他のメッセージタイプをログ出力
        else:
            logger.debug(f"Received message type: {message_type}")
    
    async def send_audio_chunk(self, audio_data: bytes):
        """音声チャンクをOpenAIに送信"""
        if not self.is_connected or not self.websocket:
            logger.warning("Not connected to OpenAI, cannot send audio")
            return
        
        try:
            # PCM16フォーマットに変換された音声データをbase64エンコード
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            message = {
                "type": "input_audio_buffer.append",
                "audio": audio_base64
            }
            
            await self.websocket.send(json.dumps(message))
            
        except Exception as e:
            logger.error(f"Failed to send audio chunk: {e}")
    
    async def send_webm_chunk(self, webm_data: bytes):
        """WebMデータをPCM16に変換して送信"""
        if not self.is_connected or not self.websocket:
            logger.warning("Not connected to OpenAI, cannot send WebM")
            return
        
        try:
            print(f"🎬 [REALTIME API] Converting WebM chunk: {len(webm_data)} bytes")
            
            # WebMをPCM16に変換
            pcm_data = PCMConverter.webm_to_pcm16(webm_data)
            if pcm_data:
                await self.send_audio_chunk(pcm_data)
                print(f"✅ [REALTIME API] Sent WebM→PCM16: {len(pcm_data)} bytes")
            else:
                print(f"❌ [REALTIME API] WebM conversion failed")
                
        except Exception as e:
            logger.error(f"Failed to send WebM chunk: {e}")
            print(f"❌ [REALTIME API] WebM send error: {e}")
    
    async def commit_audio(self):
        """音声バッファをコミットして転写を実行"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            message = {
                "type": "input_audio_buffer.commit"
            }
            await self.websocket.send(json.dumps(message))
            
        except Exception as e:
            logger.error(f"Failed to commit audio: {e}")
    
    async def clear_audio_buffer(self):
        """音声バッファをクリア"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            message = {
                "type": "input_audio_buffer.clear"
            }
            await self.websocket.send(json.dumps(message))
            
        except Exception as e:
            logger.error(f"Failed to clear audio buffer: {e}")
    
    async def disconnect(self):
        """OpenAI Realtime APIから切断"""
        if self.websocket:
            await self.websocket.close()
        self.is_connected = False
        logger.info("Disconnected from OpenAI Realtime API")


class PCMConverter:
    """WebM音声をPCM16に変換するクラス"""
    
    @staticmethod
    async def webm_to_pcm16(webm_data: bytes) -> bytes:
        """WebM音声データをPCM16に変換"""
        import subprocess
        import asyncio
        
        try:
            process = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-i', 'pipe:0',  # 入力: stdin
                '-f', 'wav',     # 出力フォーマット: WAV
                '-ar', '24000',  # サンプリングレート: 24kHz (OpenAI Realtime API推奨)
                '-ac', '1',      # チャンネル数: モノラル
                '-sample_fmt', 's16',  # サンプルフォーマット: 16bit
                'pipe:1',        # 出力: stdout
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(input=webm_data)
            
            if process.returncode == 0:
                # WAVヘッダーを除去してPCMデータのみ抽出
                if len(stdout) > 44:  # WAVヘッダーは44バイト
                    pcm_data = stdout[44:]  # ヘッダーをスキップ
                    return pcm_data
                else:
                    logger.warning("WAV data too short")
                    return b''
            else:
                logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
                return b''
                
        except Exception as e:
            logger.error(f"Error converting WebM to PCM16: {e}")
            return b''
