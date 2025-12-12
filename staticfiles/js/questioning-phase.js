// static/js/questioning-phase.js
import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const chatContainer = document.getElementById("chatContainer");
  const timerEl = document.getElementById("timer");
  const partialTranscription = document.getElementById("partialTranscription");
  const finalTranscription = document.getElementById("finalTranscription");
  const transcriptionStatus = document.getElementById("transcriptionStatus");
  
  const answerInput = document.getElementById("answerInput");
  const sendAnswerBtn = document.getElementById("sendAnswerBtn");
  const endSessionBtn = document.getElementById("endSessionBtn");
  const endSessionModal = new bootstrap.Modal(document.getElementById('endSessionModal'));
  const confirmEndBtn = document.getElementById("confirmEndBtn");
  const questionCount = document.getElementById("questionCount");
  const explanationSummary = document.getElementById("explanationSummary");

  const OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription";

  let recording = false;
  let timerId = null;
  let startAt = null;
  let currentPartialText = "";
  let currentQuestionId = null;
  let questionsAsked = 0;

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
      if (answerInput && text.trim()) {
        const currentValue = answerInput.value;
        const newValue = currentValue ? currentValue + ' ' + text : text;
        answerInput.value = newValue;
        
        // テキストエリアの高さを自動調整
        autoResize(answerInput);
        
        // 文字起こし結果が追加されたら送信ボタンの状態を更新
        updateSendButtonState();
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
      updateTranscriptionStatus("Ready");
    }
  });

  // 送信ボタンのイベントリスナー
  if (sendAnswerBtn) {
    sendAnswerBtn.addEventListener("click", async () => {
      await sendAnswer();
    });
  }

  // エンターキーでの送信（Shift+Enterで改行）
  if (answerInput) {
    answerInput.addEventListener("keydown", (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendAnswerBtn.disabled) {
          sendAnswer();
        }
      }
    });
  }

  // セッション終了ボタンのイベントリスナー
  if (endSessionBtn) {
    endSessionBtn.addEventListener("click", () => {
      endSessionModal.show();
    });
  }

  // セッション終了確認ボタンのイベントリスナー
  if (confirmEndBtn) {
    confirmEndBtn.addEventListener("click", async () => {
      await endSession();
    });
  }

  // 送信ボタンの状態を更新する関数
  function updateSendButtonState() {
    if (answerInput && sendAnswerBtn) {
      const hasText = answerInput.value.trim().length > 0;
      sendAnswerBtn.disabled = !hasText;
    }
  }
  
  // 初期チェック
  updateSendButtonState();

  // 回答入力の変更監視
  if (answerInput) {
    answerInput.addEventListener("input", updateSendButtonState);
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

  // メッセージをチャットに追加
  function appendMessage(role, text, timestamp = null) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    
    const time = timestamp || new Date().toLocaleTimeString('ja-JP', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
    
    div.innerHTML = `
      <div class="message-content">
        <strong><i class="fas ${role === "user" ? "fa-user" : "fa-robot"} me-1"></i>${role === "user" ? "あなた" : "AI面接官"}:</strong>
        ${escapeHtml(text)}
      </div>
      <div class="message-time">${time}</div>
    `;
    
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[m]));
  }

  // 初期状態で文字起こしステータスを設定
  updateTranscriptionStatus("Ready");

  // 回答を送信
  async function sendAnswer() {
    const answerText = answerInput.value.trim();
    
    if (!answerText) {
      alert("回答を入力してください。");
      return;
    }

    // ユーザーメッセージを表示
    appendMessage("user", answerText);
    
    // 入力エリアをクリア
    answerInput.value = "";
    updateSendButtonState();

    // 送信ボタンを一時的に無効化
    sendAnswerBtn.disabled = true;
    sendAnswerBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>送信中...';

    try {
      // CSRFトークンを取得
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

      // 回答を保存して次の質問を取得
      const response = await fetch('/api/interview/answers/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          session_id: window.sessionId,
          content: answerText,
          question_id: currentQuestionId
        })
      });

      if (!response.ok) {
        throw new Error(`送信エラー: ${response.status}`);
      }

      const data = await response.json();
      
      // 質問数を更新
      questionsAsked++;
      if (questionCount) {
        questionCount.textContent = questionsAsked;
      }

      // AI面接官の次の質問を表示（少し遅延を入れて自然に）
      setTimeout(() => {
        if (data.next_question) {
          appendMessage("ai", data.next_question.content);
          currentQuestionId = data.next_question.id;
        } else {
          // 質問が終了した場合
          appendMessage("ai", "ありがとうございました。これですべての質問が終了しました。お疲れ様でした！");
          // セッション終了ボタンを強調
          endSessionBtn.classList.add('btn-warning');
          endSessionBtn.innerHTML = '<i class="fas fa-star me-1"></i>セッション終了（推奨）';
        }
      }, 1000);

    } catch (error) {
      console.error("送信エラー:", error);
      alert(`エラーが発生しました: ${error.message}`);
    } finally {
      // ボタンを元の状態に戻す
      sendAnswerBtn.disabled = false;
      sendAnswerBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>送信';
      updateSendButtonState();
    }
  }

  // セッションを終了
  async function endSession() {
    // 終了ボタンを無効化
    confirmEndBtn.disabled = true;
    confirmEndBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>終了中...';

    try {
      // CSRFトークンを取得
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

      // セッション終了API呼び出し
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/end_session/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        }
      });

      if (!response.ok) {
        throw new Error(`終了エラー: ${response.status}`);
      }

      // ホームページへリダイレクト
      window.location.href = '/';

    } catch (error) {
      console.error("終了エラー:", error);
      alert(`エラーが発生しました: ${error.message}`);
    } finally {
      // ボタンを元の状態に戻す
      confirmEndBtn.disabled = false;
      confirmEndBtn.innerHTML = '<i class="fas fa-check me-1"></i>終了する';
    }
  }

  // 説明の要約を読み込む
  async function loadExplanationSummary() {
    try {
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/explanation_summary/`);
      
      if (response.ok) {
        const data = await response.json();
        if (explanationSummary && data.summary) {
          explanationSummary.textContent = data.summary;
        }
      } else {
        if (explanationSummary) {
          explanationSummary.textContent = "説明の要約を読み込めませんでした。";
        }
      }
    } catch (error) {
      console.error("要約読み込みエラー:", error);
      if (explanationSummary) {
        explanationSummary.textContent = "説明の要約を読み込めませんでした。";
      }
    }
  }

  // 最初の質問を読み込む（履歴がない場合のみ）
  async function loadFirstQuestion() {
    try {
      // まず既存の質問があるかチェック
      const historyResponse = await fetch(`/api/interview/sessions/${window.sessionId}/questions/`);
      
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        const questions = historyData.questions || [];
        
        // 既に質問がある場合は最初の質問を読み込まない
        if (questions.length > 0) {
          return;
        }
      }
      
      // 質問がない場合のみ最初の質問を読み込む
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/first_question/`);
      
      if (response.ok) {
        const data = await response.json();
        if (data.question) {
          setTimeout(() => {
            appendMessage("ai", data.question.content);
            currentQuestionId = data.question.id;
          }, 2000); // 2秒後に最初の質問を表示
        }
      }
    } catch (error) {
      console.error("最初の質問読み込みエラー:", error);
      setTimeout(() => {
        appendMessage("ai", "申し訳ございませんが、質問の読み込みでエラーが発生しました。ページを再読み込みしてください。");
      }, 2000);
    }
  }

  // 質問・回答履歴を読み込む
  async function loadQuestionHistory() {
    try {
      console.log("質問履歴を読み込み中...", window.sessionId);
      const response = await fetch(`/api/interview/sessions/${window.sessionId}/questions/`);
      
      console.log("質問履歴API応答:", response.status);
      if (response.ok) {
        const data = await response.json();
        console.log("質問履歴データ:", data);
        const questions = data.questions || [];
        
        // 質問と回答の履歴をチャットに表示
        questions.forEach(question => {
          if (question.content) {
            appendMessage("ai", question.content);
            
            // 回答があれば表示
            if (question.answer_text) {
              appendMessage("user", question.answer_text);
            }
          }
        });
        
        // 最新の質問IDを設定
        if (questions.length > 0) {
          const lastQuestion = questions[questions.length - 1];
          if (!lastQuestion.answer_text) {
            currentQuestionId = lastQuestion.id;
          }
        }
      } else {
        console.error("質問履歴の取得に失敗:", response.status, response.statusText);
      }
    } catch (error) {
      console.error("質問履歴読み込みエラー:", error);
    }
  }

  // 初期化処理
  loadExplanationSummary();
  loadQuestionHistory();
  loadFirstQuestion();
});
