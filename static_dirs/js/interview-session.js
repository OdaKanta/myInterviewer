// static/js/interview-session.js

import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  // --- HTML要素の取得 ---
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
  const submitExplanationBtn = document.getElementById("submitExplanation");
  
  // 現在のフェーズに応じた入力エリアを取得
  const explanationInput = document.getElementById("explanationInput");
  const answerInput = document.getElementById("answerInput"); // interview.htmlには存在しない可能性あり
  const currentInput = explanationInput || answerInput; // 説明フェーズでは explanationInput が使われる

  // 終了/中断ボタン (interview.htmlには存在しないため、ここでは null の可能性あり)
  const endSessionBtn = document.getElementById("endSessionBtn");
  const confirmEndBtn = document.getElementById("confirmEndBtn");
  const pauseSessionBtn = document.getElementById("pauseSessionBtn"); 

  // ★★★ フローチャート用の「状態」変数（宝箱） ★★★
  // セッションが意図的に終了/中断されたかを追跡するフラグ
  let sessionIntentionallyEnding = false; 

  // デバッグ用ログ
  console.log("DOM elements:", {
    correctedText: !!correctedText,
    correctBtn: !!correctBtn,
    explanationInput: !!explanationInput,
    pauseSessionBtn: !!pauseSessionBtn,
    endSessionBtn: !!endSessionBtn
  });


  const OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription"

  let recording = false;
  let timerId = null;
  let startAt = null;
  let currentPartialText = "";

  // --- Realtime WS Client ---
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
      
      if (currentInput && text.trim()) {
        const currentValue = currentInput.value;
        const newValue = currentValue ? currentValue + ' ' + text : text;
        currentInput.value = newValue;
        
        autoResize(currentInput);
        
        if (currentInput === explanationInput) {
          updateCorrectButtonState();
        }
      }
      
      currentPartialText = "";
      if (partialTranscription) {
        partialTranscription.textContent = "";
      }
      
      updateTranscriptionStatus("完了");
    }
  });

  // --- 録音ボタンの処理 ---
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

  // --- 校正機能の処理 ---
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
      correctBtn.style.display = 'inline-block';
    }
  }
  
  // 初期チェック
  updateCorrectButtonState();

  // 説明入力の変更監視（校正ボタンの有効/無効切り替え）
  if (explanationInput) {
    explanationInput.addEventListener("input", updateCorrectButtonState);
  }

  // --- セッション終了/中断のロジック ---

  // ★セッション情報のローカルストレージ破棄関数★
  function clearSessionLocalStorage() {
    console.log("Clearing all session data from LocalStorage.");
    localStorage.removeItem('interview_material_id');
    localStorage.removeItem('interview_session_id');
    localStorage.removeItem('interview_current_node_id');
    localStorage.removeItem('interview_uncleared_node_ids');
    localStorage.removeItem('interview_next_question');
    localStorage.removeItem('interview_consec_fail_count');
    localStorage.removeItem('interview_session_history');
    localStorage.removeItem('socratic_stage');
    localStorage.removeItem('interview_completed');
  }

  // 一時中断処理（ローカルストレージをクリアせずに離脱）
  if (pauseSessionBtn) {
    pauseSessionBtn.addEventListener("click", pauseSession);
  }
  async function pauseSession() {
    sessionIntentionallyEnding = true; 
    console.log("Session paused. Returning to home (Data kept).");
    
    if (recording) {
      await rtc.stop();
      clearInterval(timerId);
    }
    
    // ローカルストレージはクリアしない
    window.location.href = '/';
  }


  // ★★★ 意図しない離脱を検出する処理 (BFcache対策込み) ★★★
  
  // 1. beforeunload (タブを閉じるなど、完全にページが破棄されるとき)
  window.addEventListener('beforeunload', (e) => {
    if (!sessionIntentionallyEnding) {
      console.log("Unintentional exit detected (via beforeunload). Clearing local storage.");
      clearSessionLocalStorage();
      // e.returnValue = 'セッションが進行中です。ページを離れてもよろしいですか？'; // 必要に応じて警告を有効化
    }
  });
  
  // 2. pagehide (ロゴリンククリックなど、BFcacheでページが保存されるとき)
  window.addEventListener('pagehide', (e) => {
    // e.persisted が false、またはセッションが意図的に終了されていない場合
    // 通常のリンククリックによるホーム画面への遷移は、BFcacheに保存される（e.persisted=true）可能性が高いが、
    // それが「意図的な中断」でなければセッションを破棄する。
    
    if (!sessionIntentionallyEnding) {
      console.log("Unintentional exit detected (via pagehide/BFcache). Clearing local storage.");
      clearSessionLocalStorage();
    }
  });
  // ★★★ 意図しない離脱処理ここまで ★★★
  

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