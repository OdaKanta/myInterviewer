# realtime_session.py
import os
import asyncio
import json
import base64
import websockets
from django.conf import settings


OPENAI_API_KEY = settings.OPENAI_API_KEY
# モデル/エンドポイントは必要に応じて調整
OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription"

class RealtimeSession:
    """
    OpenAI Realtime WS と常時接続するセッション。
    - append/commit でWAVチャンクを投入
    - 入力音声の逐次文字起こしイベントを購読
    - partial/finalテキストを await で受け取れるAPIを提供
    """
    def __init__(self, language: str = "ja"):
        self.language = language
        self.ws = None
        self._rx_task = None
        self._connected = asyncio.Event()
        # 逐次結果を受け取るキュー（partial を頻繁に、final をたまに）
        self.partial_queue = asyncio.Queue()
        self.final_queue = asyncio.Queue()
        # セッション内での保険（エラーなど）
        self._stop = False

    async def connect(self):
        self.ws = await websockets.connect(
            OPENAI_RT_WS,
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1",
            },
            max_size=20 * 1024 * 1024,
        )

        # 入力音声の自動STTを有効化（WAVを送る）
        session_update = {
            "type": "session.update",
            "session": {
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe",  # 低遅延寄り
                    "language": self.language
                },
                "input_audio_format": "wav"
            }
        }
        await self.ws.send(json.dumps(session_update))

        # 受信ループ開始
        self._rx_task = asyncio.create_task(self._recv_loop())
        self._connected.set()

    async def _recv_loop(self):
        try:
            async for msg in self.ws:
                # 受信はJSONイベント
                try:
                    event = json.loads(msg)
                    print(event)
                except Exception:
                    continue

                etype = event.get("type", "")

                # --- 代表的な入力STTイベントの取り扱い ---
                # ドキュメント上はイベント名が増える可能性があるため、
                # transcript/ text 系のフィールドも広く拾っておく。
                # ref: Realtime ガイド（音声バッファとセッション更新）:contentReference[oaicite:1]{index=1}

                # 例: "input_audio_transcription.delta" / "input_audio_transcription.completed"
                if "transcription" in etype or "transcript" in etype:
                    # よくあるパターン：{ ..., "text": "..." } or { ..., "transcript": "..." }
                    text = (
                        event.get("text")
                        or event.get("transcript")
                        or event.get("delta", {}).get("text")
                        or ""
                    )
                    if not text:
                        continue

                    if "completed" in etype or event.get("final", False):
                        await self.final_queue.put(text)
                    else:
                        await self.partial_queue.put(text)

                # 一部の環境では response.* 側にユーザー入力の写しが来ることもあるので保険
                elif etype.endswith(".delta") or etype.endswith(".completed"):
                    text = (
                        event.get("text")
                        or event.get("delta", {}).get("text")
                        or ""
                    )
                    if text:
                        if etype.endswith(".completed"):
                            await self.final_queue.put(text)
                        else:
                            await self.partial_queue.put(text)
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            # ログなど
            print(f"[Realtime _recv_loop] error: {e}")

    async def close(self):
        self._stop = True
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        if self._rx_task:
            self._rx_task.cancel()

    async def push_wav_and_get_partial(self, wav_bytes: bytes, request_response: bool = False) -> str:
        """
        WAVチャンクを append→commit。直近の partial を1本だけ待って返す。
        UI更新用のチラ見せに使う想定。
        """
        print("Pushing WAV and waiting for partial...")

        await self._connected.wait()
        b64 = base64.b64encode(wav_bytes).decode("ascii")

        # 1) 追記
        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": b64
        }))
        # 2) コミット
        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.commit"
        }))

        # ★ 重要：出力を開始するトリガ（毎回でOK）
        if request_response:
            await self.ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text"],
                    "instructions": "Transcribe user audio as plain text."
                }
            }))

        # partial をタイムアウト付きで1つだけ拾う
        try:
            # 300〜800msくらいが実運用でバランス良い
            txt = await asyncio.wait_for(self.partial_queue.get(), timeout=1.0)
            print(f"Partial transcription received: {txt}")
            return txt
        except asyncio.TimeoutError:
            print("No partial transcription received within timeout.")
            return ""

    async def push_wav_and_get_final(self, wav_bytes: bytes, timeout: float = 3.0) -> str:
        """
        WAVチャンクを append→commit。確定（final）を待って返す。
        連続会話なら partial をUIへ、final は確定ログ用に、など併用が現実的。
        """
        await self._connected.wait()
        b64 = base64.b64encode(wav_bytes).decode("ascii")

        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": b64
        }))
        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.commit"
        }))

        try:
            txt = await asyncio.wait_for(self.final_queue.get(), timeout=timeout)
            return txt
        except asyncio.TimeoutError:
            return ""
