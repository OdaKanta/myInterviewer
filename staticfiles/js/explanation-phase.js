// static/js/explanation-phase.js
import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const timerEl = document.getElementById("timer");
  const partialTranscription = document.getElementById("partialTranscription");
  const finalTranscription = document.getElementById("finalTranscription");
  const transcriptionStatus = document.getElementById("transcriptionStatus");
  
  const explanationInput = document.getElementById("explanationInput");
  const correctedText = document.getElementById("correctedText");
  const correctBtn = document.getElementById("correctBtn");
  const proceedToQuestioningBtn = document.getElementById("proceedToQuestioningBtn");
  const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
  const confirmProceedBtn = document.getElementById("confirmProceedBtn");

  const OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription";

  let recording = false;
  let timerId = null;
  let startAt = null;
  let currentPartialText = "";

  const rtc = new RealtimeWSClient({
    wsUrl: OPENAI_RT_WS,
    onStatus: (status) => { 
      updateTranscriptionStatus(status);
    },
    onPartialText: (delta) => {
      console.log("Partial text received:", delta);
      currentPartialText += delta;
      if (partialTranscription) {
        partialTranscription.textContent = currentPartialText;
      }
      updateTranscriptionStatus("文字起こし中...");
    },
    onFinalText: (text) => {
      console.log("Final text received:", text);
      if (finalTranscription) {
        finalTranscription.textContent = text;
      }
      
      // 入力エリアに文字起こし結果を追加
      if (explanationInput && text.trim()) {
        const currentValue = explanationInput.value;
        const newValue = currentValue ? currentValue + ' ' + text : text;
        explanationInput.value = newValue;
        
        // テキストエリアの高さを自動調整
        autoResize(explanationInput);
        
        // 文字起こし結果が追加されたら校正ボタンの状態を更新
        updateCorrectButtonState();
      }
      
      // 部分的な文字起こしをクリア
      currentPartialText = "";
      if (partialTranscription) {
        partialTranscription.textContent = "";
      }
      
      updateTranscriptionStatus("完了");
    }
  });

  // 録音ボタンのイベントリスナー
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

  // 深堀フェーズへ進むボタンのイベントリスナー
  if (proceedToQuestioningBtn) {
    proceedToQuestioningBtn.addEventListener("click", () => {
      if (correctedText.value.trim()) {
        confirmModal.show();
      } else {
        alert("まず校正を実行してから深堀フェーズへ進んでください。");
      }
    });
  }

  // 確認ボタンのイベントリスナー
  if (confirmProceedBtn) {
    confirmProceedBtn.addEventListener("click", async () => {
      await saveExplanationAndProceed();
    });
  }
  
  // 校正ボタンの状態を更新する関数
  function updateCorrectButtonState() {
    if (explanationInput && correctBtn) {
      const hasText = explanationInput.value.trim().length > 0;
      correctBtn.disabled = !hasText;
    }
  }

  // 深堀フェーズへ進むボタンの状態を更新する関数
  function updateProceedButtonState() {
    if (correctedText && proceedToQuestioningBtn) {
      const hasCorrectedText = correctedText.value.trim().length > 0;
      proceedToQuestioningBtn.disabled = !hasCorrectedText;
    }
  }
  
  // 初期チェック
  updateCorrectButtonState();
  updateProceedButtonState();

  // 説明入力の変更監視
  if (explanationInput) {
    explanationInput.addEventListener("input", updateCorrectButtonState);
  }

  // 校正結果の変更監視
  if (correctedText) {
    correctedText.addEventListener("input", updateProceedButtonState);
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
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/correct/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          text: text,
          correction_type: 'explanation'
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.success) {
        correctedText.value = data.corrected_text;
        // 校正完了後に深堀フェーズボタンの状態を更新
        updateProceedButtonState();
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
      updateCorrectButtonState();
    }
  }

  // 説明を保存して深堀フェーズへ進む
  async function saveExplanationAndProceed() {
    const explanationText = correctedText.value.trim();
    
    if (!explanationText) {
      alert("保存する説明文がありません。");
      return;
    }

    // 保存ボタンを無効化
    confirmProceedBtn.disabled = true;
    confirmProceedBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>保存中...';

    try {
      // CSRFトークンを取得
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

      // 説明を保存
      const saveResponse = await fetch('/api/interview/explanations/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          session_id: window.sessionId,
          content: explanationText
        })
      });

      if (!saveResponse.ok) {
        throw new Error(`保存エラー: ${saveResponse.status}`);
      }

      // 質問フェーズを開始
      const questioningResponse = await fetch(`/api/interview/sessions/${window.sessionId}/start_questioning_phase/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        }
      });

      if (!questioningResponse.ok) {
        throw new Error(`フェーズ移行エラー: ${questioningResponse.status}`);
      }

      // 深堀フェーズページへ移動
      window.location.href = `/interview/${window.sessionId}/questioning/`;

    } catch (error) {
      console.error("保存/移行エラー:", error);
      alert(`エラーが発生しました: ${error.message}`);
    } finally {
      // ボタンを元の状態に戻す
      confirmProceedBtn.disabled = false;
      confirmProceedBtn.innerHTML = '<i class="fas fa-save me-1"></i>保存して進む';
    }
  }
});
