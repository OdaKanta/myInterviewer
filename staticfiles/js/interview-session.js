// static/js/interview-session.js
import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const chatArea = document.getElementById("chatContainer");
  const sessionStatus = document.getElementById("sessionStatus");
  const timerEl = document.getElementById("timer");
  const partialTranscription = document.getElementById("partialTranscription");
  const finalTranscription = document.getElementById("finalTranscription");
  const transcriptionStatus = document.getElementById("transcriptionStatus");
  
  // 新しい2ペイン構成の要素
  const correctedText = document.getElementById("correctedText");
  const correctBtn = document.getElementById("correctBtn");

  // 現在のフェーズに応じた入力エリアを取得
  const explanationInput = document.getElementById("explanationInput");
  const answerInput = document.getElementById("answerInput");
  const currentInput = explanationInput || answerInput;

  // デバッグ用ログ
  console.log("DOM elements:", {
    correctedText: !!correctedText,
    correctBtn: !!correctBtn,
    explanationInput: !!explanationInput
  });

  // **ここをあなたの定義に合わせて**：
  // OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription&model=gpt-4o-realtime-preview"
  const OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription"

  let recording = false;
  let timerId = null;
  let startAt = null;
  let currentPartialText = "";

  const rtc = new RealtimeWSClient({
    wsUrl: OPENAI_RT_WS,
    onStatus: (status) => { 
      // セッションステータスと文字起こしステータスを更新
      updateTranscriptionStatus(status);
    },
    onPartialText: (delta) => {
      console.log("Partial text received:", delta);
      currentPartialText += delta;
      // 逐次文字起こし結果を表示
      if (partialTranscription) {
        partialTranscription.textContent = currentPartialText;
      }
      updateTranscriptionStatus("文字起こし中...");
    },
    onFinalText: (text) => {
      console.log("Final text received:", text);
      // 確定した文字起こし結果を表示
      if (finalTranscription) {
        finalTranscription.textContent = text;
      }
      
      // 入力エリアに文字起こし結果を追加
      if (currentInput && text.trim()) {
        const currentValue = currentInput.value;
        const newValue = currentValue ? currentValue + ' ' + text : text;
        currentInput.value = newValue;
        
        // テキストエリアの高さを自動調整
        autoResize(currentInput);
        
        // 文字起こし結果が追加されたら校正ボタンの状態を更新
        if (currentInput === explanationInput) {
          updateCorrectButtonState();
        }
      }
      
      
      // 部分的な文字起こしをクリア
      currentPartialText = "";
      if (partialTranscription) {
        partialTranscription.textContent = "";
      }
      
      updateTranscriptionStatus("完了");
    }
  });

  recordBtn.addEventListener("click", async () => {
    if (!recording) {
      recording = true;
      recordBtn.classList.add("recording");
      recordBtn.innerHTML = `<i class="fas fa-stop"></i>`;
      recordBtn.title = "録音停止";

      updateTranscriptionStatus("録音中...");
      await rtc.start();

      startAt = Date.now();
      timerId = setInterval(() => {
        const s = Math.floor((Date.now() - startAt) / 1000);
        const mm = String(Math.floor(s / 60)).padStart(2, "0");
        const ss = String(s % 60).padStart(2, "0");
        timerEl.textContent = `${mm}:${ss}`;
      }, 250);
    } else {
      recording = false;
      recordBtn.classList.remove("recording");
      recordBtn.innerHTML = `<i class="fas fa-microphone"></i>`;
      recordBtn.title = "音声録音";

      await rtc.stop();
      clearInterval(timerId);
      timerEl.textContent = "00:00";
      updateTranscriptionStatus("Stop");
    }
  });

  // 校正ボタンのイベントリスナー
  if (correctBtn) {
    correctBtn.addEventListener("click", async () => {
      await performCorrection();
    });
  }
  
  // 校正ボタンの状態を更新する関数
  function updateCorrectButtonState() {
    if (explanationInput && correctBtn) {
      const hasText = explanationInput.value.trim().length > 0;
      correctBtn.disabled = !hasText;
      correctBtn.style.display = 'inline-block'; // ボタンを確実に表示
    }
  }
  
  // 初期チェック
  updateCorrectButtonState();

  // 説明入力の変更監視（校正ボタンの有効/無効切り替え）
  if (explanationInput) {
    explanationInput.addEventListener("input", updateCorrectButtonState);
  }

  function updateTranscriptionStatus(status) {
    if (transcriptionStatus) {
      transcriptionStatus.textContent = status;
      
      // ステータスに応じてバッジの色を変更
      transcriptionStatus.className = 'badge ';
      if (status.includes('録音中') || status.includes('文字起こし中')) {
        transcriptionStatus.className += 'bg-success';
      } else if (status.includes('エラー') || status.includes('error')) {
        transcriptionStatus.className += 'bg-danger';
      } else if (status.includes('完了')) {
        transcriptionStatus.className += 'bg-primary';
      } else if (status.includes('open') || status.includes('connecting')) {
        transcriptionStatus.className += 'bg-info';
      } else {
        transcriptionStatus.className += 'bg-secondary';
      }
    }
  }

  function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.innerHTML = `
      <strong><i class="fas ${role === "user" ? "fa-user" : "fa-robot"} me-1"></i>${role === "user" ? "あなた" : "システム"}:</strong>
      ${escapeHtml(text)}
    `;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[m]));
  }

  // セッションステータスの初期設定
  if (sessionStatus) {
    // 既存のステータステキストを保持するか、デフォルト値を設定
    if (!sessionStatus.textContent.trim()) {
      sessionStatus.textContent = "準備完了";
    }
  }

  // 初期状態で文字起こしステータスを設定
  updateTranscriptionStatus("Stop");

  // GPTを使用したテキスト校正機能
  async function performCorrection() {
    if (!correctBtn || !explanationInput || !correctedText) {
      console.error("校正機能の必要な要素が見つかりません");
      return;
    }

    const text = explanationInput.value.trim();
    if (!text) {
      alert("校正するテキストを入力してください");
      return;
    }

    // ボタンを無効化して処理中表示
    correctBtn.disabled = true;
    const originalText = correctBtn.textContent;
    correctBtn.textContent = "校正中...";
    correctedText.value = "校正中です...";

    try {
      // CSRFトークンを取得
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value 
                     || document.querySelector('meta[name=csrf-token]')?.getAttribute('content')
                     || '';

      // バックエンドのGPT校正APIを呼び出し
      const response = await fetch(`/api/interview/sessions/${window.sessionId || sessionId}/correct/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          text: text,
          correction_type: 'explanation' // 説明文の校正
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.success) {
        correctedText.value = data.corrected_text;
      } else {
        throw new Error(data.error || "校正に失敗しました");
      }

    } catch (error) {
      console.error("校正エラー:", error);
      correctedText.value = "";
      alert(`校正エラー: ${error.message}`);
    } finally {
      // ボタンを元の状態に戻す
      correctBtn.disabled = false;
      correctBtn.textContent = originalText;
    }
  }
});

