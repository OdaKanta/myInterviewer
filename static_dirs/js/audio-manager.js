
// static/js/audio-manager.js
// OpenAI Realtime WebSocket Client for Audio Transcription

/**
 * AudioWorkletProcessor for PCM audio processing
 */
const AUDIO_WORKLET_PROCESSOR_CODE = `
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.sampleRate = 24000;
    this.chunkSize = this.sampleRate * 0.1; // 100ms chunks
    this.buffer = [];
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input[0]) {
      const float32Data = input[0];
      this.buffer.push(...float32Data);

      while (this.buffer.length >= this.chunkSize) {
        const chunk = this.buffer.slice(0, this.chunkSize);
        this.buffer = this.buffer.slice(this.chunkSize);

        const int16Buffer = new Int16Array(chunk.length);
        for (let i = 0; i < chunk.length; i++) {
          int16Buffer[i] = Math.max(-1, Math.min(1, chunk[i])) * 0x7fff;
        }

        this.port.postMessage(int16Buffer.buffer, [int16Buffer.buffer]);
      }
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
`;

/**
 * OpenAI Realtime WebSocket Client
 * Handles real-time audio transcription using OpenAI's Realtime API
 */
export class RealtimeWSClient {
  constructor({ wsUrl, onPartialText, onFinalText, onStatus }) {
    this.wsUrl = wsUrl;
    this.onPartialText = onPartialText || (() => {});
    this.onFinalText = onFinalText || (() => {});
    this.onStatus = onStatus || (() => {});
    
    // WebSocket connection
    this.ws = null;
    this._connected = false;
    this._stopped = false;
    
    // Audio processing
    this.stream = null;
    this.audioCtx = null;
    this.source = null;
    this.processor = null;
    this._lastCommitTime = null;
    this._commitInterval = null;
    this._lastCommitTime = null;
    this._hasInitialCommit = false;
    
    // Audio configuration
    this.config = {
      sampleRate: 24000,
      channelCount: 1,
      chunkSize: 0.1 // 100ms chunks
    };
  }

  /**
   * Start the realtime transcription session
   */
  async start() {
    try {
      const ephemeralToken = await this._getEphemeralToken();
      await this._connectWebSocket(ephemeralToken);
    } catch (error) {
      this.onStatus(`Error starting session: ${error.message}`);
      throw error;
    }
  }

  /**
   * Stop the realtime transcription session
   */
  async stop() {
    this._stopAudioProcessing();
    this._closeWebSocket();
  }

  /**
   * Get ephemeral token from the server
   * @private
   */
  async _getEphemeralToken() {
    this.onStatus("Getting ephemeral token...");
    
    const response = await fetch(`/api/interview/sessions/${window.sessionId}/realtime/session/`);
    const { client_secret } = await response.json();
    
    if (!client_secret?.value) {
      throw new Error("Ephemeral token missing");
    }
    
    return client_secret.value;
  }

  /**
   * Connect to OpenAI Realtime WebSocket
   * @private
   */
  async _connectWebSocket(token) {
    this.onStatus("Connecting to WebSocket...");
    
    const protocols = [
      "realtime",
      `openai-insecure-api-key.${token}`,
      "openai-beta.realtime-v1"
    ];
    
    this.ws = new WebSocket(this.wsUrl, protocols);
    
    this.ws.onopen = async () => {
      console.log("WebSocket connection established");
      this._connected = true;
      this.onStatus("Connected");
      
      await this._configureSession();
      await this._startAudioProcessing();
      
    };

    this.ws.onmessage = (event) => this._handleWebSocketMessage(event);
    this.ws.onerror = (error) => this.onStatus("WebSocket error");
    this.ws.onclose = (event) => this._handleWebSocketClose(event);

  }

  /**
   * Configure the transcription session
   * @private
   */
  async _configureSession() {
    const configMessage = {
      type: "transcription_session.update",
      session: {
        input_audio_transcription: {
          model: "gpt-4o-mini-transcribe",
          language: "ja",
        },
        input_audio_noise_reduction: { type: "near_field" },
        turn_detection: {
          type: "semantic_vad",
          eagerness: "high",
        },
        // turn_detection: {
        //   type: "server_vad",
        //   threshold: 0.5,
        //   prefix_padding_ms: 300,
        //   silence_duration_ms: 200,
        // },
      },
    };
    
    this._sendMessage(configMessage);
  }

  /**
   * Handle incoming WebSocket messages
   * @private
   */
  _handleWebSocketMessage(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      return; // Ignore non-JSON messages
    }

    const messageType = message.type;
    console.log("Received WebSocket message:", message);

    // Handle partial transcription (delta messages)
    if (messageType === "conversation.item.input_audio_transcription.delta" && message.delta) {
      this.onPartialText(message.delta);
    }

    // Handle final transcription (completed messages)
    if (messageType === "conversation.item.input_audio_transcription.completed" && message.transcript) {
      this.onFinalText(message.transcript);
    }

  }

  /**
   * Handle WebSocket close event
   * @private
   */
  _handleWebSocketClose(event) {
    this._connected = false;
    const reason = event.reason || "(no reason provided)";
    if (reason === "(no reason provided)") {
      this.onStatus(`Stop`);
    }
    else {
      this.onStatus(`WebSocket closed: code=${event.code}, reason=${reason}`);
    }

    if (!this._stopped) {
      this._stopAudioProcessing();
    }
  }

  /**
   * Start audio processing using AudioWorklet
   * @private
   */
  async _startAudioProcessing() {
    this.onStatus("Requesting microphone access...");
    
    try {
      // Get user media with specific audio constraints
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: this.config.sampleRate,
          channelCount: this.config.channelCount
        }
      });

      // Create audio context
      this.audioCtx = new AudioContext({ 
        sampleRate: this.config.sampleRate 
      });
      this.source = this.audioCtx.createMediaStreamSource(this.stream);

      // Setup AudioWorklet processor
      await this._setupAudioProcessor();
      
      this.onStatus("Microphone active");
      
    } catch (error) {
      console.error("Failed to start audio processing:", error);
      this.onStatus(`Microphone error: ${error.message}`);
      throw error;
    }
  }

  /**
   * Setup AudioWorklet processor
   * @private
   */
  async _setupAudioProcessor() {
    const blob = new Blob([AUDIO_WORKLET_PROCESSOR_CODE], {
      type: "application/javascript"
    });
    const workletUrl = URL.createObjectURL(blob);
    
    try {
      await this.audioCtx.audioWorklet.addModule(workletUrl);
      this.processor = new AudioWorkletNode(this.audioCtx, 'pcm-processor');
      
      this.processor.port.onmessage = (event) => {
        this._handleAudioData(event.data);
      };

      this.source.connect(this.processor);
      this.processor.connect(this.audioCtx.destination);
      
    } finally {
      URL.revokeObjectURL(workletUrl);
    }
  }

  /**
   * Handle audio data from AudioWorklet
   * @private
   */
  _handleAudioData(audioBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const base64Audio = this._arrayBufferToBase64(audioBuffer);
      
      // 音声データを送信
      this._sendMessage({
        type: "input_audio_buffer.append",
        audio: base64Audio
      });
      
    }
  }

  /**
   * Start periodic commit interval
   * @private
   */
  _startPeriodicCommit() {
    // 200msごとにcommitを送信
    this._commitInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this._sendMessage({ type: "input_audio_buffer.commit" });
        console.log("Periodic commit sent");
      }
    }, 200);
    
    console.log("Started periodic commit interval (200ms)");
  }

  /**
   * Stop periodic commit interval
   * @private
   */
  _stopPeriodicCommit() {
    if (this._commitInterval) {
      clearInterval(this._commitInterval);
      this._commitInterval = null;
      console.log("Stopped periodic commit interval");
    }
  }

  /**
   * Stop audio processing
   * @private
   */
  _stopAudioProcessing() {
    if (this._stopped) return;
    
    this._stopped = true;
    
    // 定期commitを停止
    this._stopPeriodicCommit();
    
    try {
      if (this.processor) {
        if (this.processor instanceof AudioWorkletNode) {
          this.processor.port.onmessage = null;
        }
        this.processor.disconnect();
      }
    } catch (error) {
      console.warn("Error disconnecting processor:", error);
    }

    try {
      this.source?.disconnect();
    } catch (error) {
      console.warn("Error disconnecting source:", error);
    }

    try {
      if (this.audioCtx && this.audioCtx.state !== "closed") {
        this.audioCtx.close();
      }
    } catch (error) {
      console.warn("Error closing audio context:", error);
    }

    try {
      this.stream?.getTracks()?.forEach(track => track.stop());
    } catch (error) {
      console.warn("Error stopping media tracks:", error);
    }

    // Reset audio objects
    this.processor = null;
    this.source = null;
    this.audioCtx = null;
    this.stream = null;
    this._lastCommitTime = null;
    this._commitInterval = null;
    this._hasInitialCommit = false;
    this._lastCommitTime = null;
  }

  /**
   * Close WebSocket connection
   * @private
   */
  _closeWebSocket() {
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.close();
      }
    } catch (error) {
      console.warn("Error closing WebSocket:", error);
    }
  }

  /**
   * Send message to WebSocket
   * @private
   */
  _sendMessage(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
    else {
      console.warn("WebSocket is not open. Message not sent:", message);
    }
  }

  /**
   * Convert ArrayBuffer to Base64 string
   * @private
   */
  _arrayBufferToBase64(arrayBuffer) {
    const uint8Array = new Uint8Array(arrayBuffer);
    let binary = '';
    
    for (let i = 0; i < uint8Array.length; i++) {
      binary += String.fromCharCode(uint8Array[i]);
    }
    
    return btoa(binary);
  }
}
