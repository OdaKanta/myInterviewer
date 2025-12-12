// static/js/explanation-phase.js
import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  // --- HTML要素の取得 ---
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

  // --- 音声認識クライアント ---
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
      
      if (explanationInput && text.trim()) {
        const currentValue = explanationInput.value;
        const newValue = currentValue ? currentValue + ' ' + text : text;
        explanationInput.value = newValue;
        
        autoResize(explanationInput);
        
        // ★★★ テキストが追加されたら、両方のボタンの状態を更新 ★★★
        updateCorrectButtonState();
        updateProceedButtonState();
      }
      
      currentPartialText = "";
      if (partialTranscription) {
        partialTranscription.textContent = "";
      }
      
      updateTranscriptionStatus("完了");
    }
  });

  // --- 録音ボタンのイベント ---
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

  // --- 校正ボタンのイベント ---
  if (correctBtn) {
    correctBtn.addEventListener("click", async () => {
      await performCorrection();
    });
  }

  // --- ▼▼▼ 「深堀へ進む」ボタンのイベント (「原文」を見るように変更) ▼▼▼ ---
  if (proceedToQuestioningBtn) {
    proceedToQuestioningBtn.addEventListener("click", () => {
      if (explanationInput.value.trim()) { // ★「原文」をチェック
        confirmModal.show();
      } else {
        alert("まず「文字起こし原文」に説明を入力してください。");
      }
    });
  }

  // --- 確認ボタンのイベント ---
  if (confirmProceedBtn) {
    confirmProceedBtn.addEventListener("click", async () => {
      await saveExplanationAndProceed();
    });
  }
  
  // --- ▼▼▼ 「校正」ボタンの有効/無効 (「原文」を見る) ▼▼▼ ---
  function updateCorrectButtonState() {
    if (explanationInput && correctBtn) {
      const hasText = explanationInput.value.trim().length > 0;
      correctBtn.disabled = !hasText;
    }
  }

  // --- ▼▼▼ 「深堀へ進む」ボタンの有効/無効 (「原文」を見るように変更) ▼▼▼ ---
  function updateProceedButtonState() {
    if (explanationInput && proceedToQuestioningBtn) { // ★「原文」をチェック
      const hasText = explanationInput.value.trim().length > 0;
      proceedToQuestioningBtn.disabled = !hasText;
    }
  }
  
  // --- 初期チェック ---
  updateCorrectButtonState();
  updateProceedButtonState();

  // --- ▼▼▼ 「原文」入力の監視 (両方のボタンを更新するように変更) ▼▼▼ ---
  if (explanationInput) {
    explanationInput.addEventListener("input", () => {
        updateCorrectButtonState();   // 「校正」ボタンの状態を更新
        updateProceedButtonState(); // 「深堀へ進む」ボタンの状態を更新
    });
  }

  // --- 補助関数 ---
  function updateTranscriptionStatus(status) {
    if (transcriptionStatus) {
      transcriptionStatus.textContent = status;
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

  updateTranscriptionStatus("Stop");

  // --- GPT校正機能 ---
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
    correctBtn.disabled = true;
    const originalText = correctBtn.textContent;
    correctBtn.textContent = "校正中...";
    correctedText.value = "校正中です...";
    try {
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/correct/`, { //
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
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
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
      correctBtn.disabled = false;
      correctBtn.textContent = originalText;
      updateCorrectButtonState();
    }
  }

  // --- ▼▼▼ 「説明保存」＆「フェーズ移行」 (あなたのフローチャートAPIを呼ぶ) ▼▼▼ ---
  async function saveExplanationAndProceed() {
    
    // ★「校正結果」 があればそちらを優先し、なければ「原文」 を使う
    const explanationText = correctedText.value.trim() ? correctedText.value.trim() : explanationInput.value.trim();
    
    if (!explanationText) {
      alert("保存する説明文がありません。");
      return;
    }

    confirmProceedBtn.disabled = true;
    confirmProceedBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>処理中...';

    try {
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
      const materialId = localStorage.getItem('interview_material_id'); // home.htmlで保存したID
      if (!materialId) {
          throw new Error('教材IDが見つかりません。ホームからやり直してください。');
      }

      // ★★★ あなたの「interview_next_step」APIを呼ぶ ★★★
      const response = await fetch(`/api/knowledge-tree/nodes/interview_next_step/`, {
        method: 'POST', // ★★★ この行を追加！ ★★★
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            'session_id': window.sessionId,
            'material_id': materialId,
            'user_answer': explanationText
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `APIエラー: ${response.status}`);
      }

      const data = await response.json();

      // ★★★ 次のページで使う「状態」をブラウザに保存 ★★★
      localStorage.setItem('interview_next_question', data.interview_next_question);
      localStorage.setItem('interview_current_node_id', data.next_node_id); 
      localStorage.setItem('interview_uncleared_node_ids', JSON.stringify(data.uncleared_node_ids));
      localStorage.setItem('interview_consec_fail_count', data.consec_fail_count);
      localStorage.setItem('socratic_stage', data.socratic_stage);

      // 深堀フェーズページへ移動
      window.location.href = `/interview/${window.sessionId}/questioning/`;

    } catch (error) {
      console.error("移行エラー:", error);
      alert(`エラーが発生しました: ${error.message}`);
      confirmProceedBtn.disabled = false;
      confirmProceedBtn.innerHTML = '<i class="fas fa-save me-1"></i>保存して進む';
    }
  }
});