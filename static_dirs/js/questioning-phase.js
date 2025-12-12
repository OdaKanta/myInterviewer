import {RealtimeWSClient} from "/static/js/audio-manager.js";

document.addEventListener("DOMContentLoaded", () => {
  // --- HTML要素の取得 ---
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
  const pauseSessionBtn = document.getElementById("pauseSessionBtn"); 
  const questionCount = document.getElementById("questionCount");
  const explanationSummary = document.getElementById("explanationSummary");

  const OPENAI_RT_WS = "wss://api.openai.com/v1/realtime?intent=transcription";

  let recording = false;
  let timerId = null;
  let startAt = null;
  let currentPartialText = "";
  let sessionIntentionallyEnding = false; 

  // ★★★ フローチャート用の「状態」変数（宝箱） ★★★
  let currentMaterialId = null;
  let currentNodeId = null;
  let unclearedNodeIds = [];
  let questionsAsked = 0;
  let consecFailCount = 0; 
  let sessionHistory = []; 
  let lastQuestionText = "";
  let socraticStage = 1;
  let interviewCompleted = false; // ★追加: セッション完了状態を保持
  // ★★★ ここまで ★★★

  const rtc = new RealtimeWSClient({
    wsUrl: OPENAI_RT_WS,
    onStatus: (status) => { 
      updateTranscriptionStatus(status);
    },
    onPartialText: (delta) => {
      currentPartialText += delta;
      if (partialTranscription) partialTranscription.textContent = currentPartialText;
      updateTranscriptionStatus("文字起こし中...");
    },
    onFinalText: (text) => {
      if (finalTranscription) finalTranscription.textContent = text;
      if (answerInput && text.trim()) {
        answerInput.value = answerInput.value ? answerInput.value + ' ' + text : text;
        autoResize(answerInput);
        updateSendButtonState();
      }
      currentPartialText = "";
      if (partialTranscription) partialTranscription.textContent = "";
      updateTranscriptionStatus("完了");
    }
  });

  // --- 録音ボタンの処理 (変更なし) ---
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

  // --- 回答送信ボタンの処理 ---
  endSessionBtn.addEventListener("click", () => {
    // セッションが完了していない場合はモーダルを表示しない（二重チェック）
    // NOTE: endSessionBtnはinterviewCompletedの状態に応じて無効化されているはずだが、念のためチェック
    if (interviewCompleted) {
      endSessionModal.show();
    }
    // 完了していない場合は、ボタンが無効なので何も起こらない
  });
  sendAnswerBtn.addEventListener("click", sendAnswer);
  answerInput.addEventListener("keydown", (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendAnswerBtn.disabled) sendAnswer();
    }
  });
  answerInput.addEventListener("input", updateSendButtonState);

  // ★★★ 回答を送信する (API呼び出しと状態更新) ★★★
  async function sendAnswer() {
    const answerText = answerInput.value.trim();
    if (!answerText) return;

    // 1. 自分の回答をチャットに表示
    appendMessage("user", answerText);
    answerInput.value = "";
    updateSendButtonState();
    sendAnswerBtn.disabled = true;
    sendAnswerBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>送信中...';
    const questionToSend = lastQuestionText || "";
    const currentQA = {
        node_id: parseInt(currentNodeId),
        question: questionToSend,
        answer: answerText
    };
    const historyToSend = [...sessionHistory, currentQA];

    try {
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

      // 2. ★「interview_next_step」APIを呼ぶ★
      const response = await fetch('/api/knowledge-tree/nodes/interview_next_step/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          'material_id': currentMaterialId,
          'user_answer': answerText,
          'current_node_id': currentNodeId,
          'uncleared_node_ids': unclearedNodeIds,
          'consec_fail_count': consecFailCount,
          'interview_session_history': historyToSend,
          'interview_next_question': questionToSend,
          'socratic_stage': socraticStage
        })
      });

      if (!response.ok) {
        throw new Error(`送信エラー: ${response.status}`);
      }

      const data = await response.json();
      
      // 3. 質問数を更新
      questionsAsked++;
      if (questionCount) questionCount.textContent = questionsAsked;

      // 4. ★返ってきた「新しい状態」で宝箱を更新し、ローカルストレージに保存★
      sessionHistory.push(currentQA); 
      currentNodeId = data.next_node_id;
      unclearedNodeIds = data.uncleared_node_ids;
      consecFailCount = data.consec_fail_count !== undefined ? data.consec_fail_count : 0;
      socraticStage = data.socratic_stage;
      interviewCompleted = data.status === 'interview_completed'; // ★更新

      // ローカルストレージに保存
      localStorage.setItem('interview_current_node_id', currentNodeId);
      localStorage.setItem('interview_uncleared_node_ids', JSON.stringify(unclearedNodeIds));
      localStorage.setItem('interview_consec_fail_count', consecFailCount);
      localStorage.setItem('interview_session_history', JSON.stringify(sessionHistory));
      lastQuestionText = data.interview_next_question || "";
      localStorage.setItem('interview_next_question', lastQuestionText);
      localStorage.setItem('socratic_stage', socraticStage);
      localStorage.setItem('interview_completed', interviewCompleted ? 'true' : 'false'); // ★追加

      // ★修正箇所1: セッション完了時にボタンの状態を更新する
      updateEndButtonState();

      // 5. AIの次の質問を表示 (少し遅延)
      setTimeout(() => {
        if (interviewCompleted) { // ★完了チェック
          appendMessage("ai", "ありがとうございました。これですべての質問が終了しました。お疲れ様でした！");
          answerInput.disabled = true;
          sendAnswerBtn.disabled = true;
          sessionIntentionallyEnding = true; // 終了状態なので、以降の離脱は意図的と見なす
        } else {
          appendMessage("ai", data.interview_next_question);
        }
      }, 1000);
    } catch (error) {
      console.error("送信エラー:", error);
      appendMessage("system", `エラーが発生しました: ${error.message}`);
    } finally {
      // 6. ボタンを元の状態に戻す
      sendAnswerBtn.disabled = false;
      sendAnswerBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>送信';
      updateSendButtonState();
    }
  }
  // --- 回答送信の処理ここまで ---

  // --- セッション終了処理 (ローカルストレージ削除とリダイレクト) ---
  confirmEndBtn.addEventListener("click", () => endSession(true)); 
  
  async function endSession(notifyServer = false) { 
    sessionIntentionallyEnding = true; 

    if (notifyServer) {
      confirmEndBtn.disabled = true;
      confirmEndBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>終了中...';
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        const response = await fetch(`/api/interview/sessions/${window.sessionId}/end_session/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
        });
        if (!response.ok) throw new Error(`終了エラー: ${response.status}`);
      } catch (error) {
        console.error("サーバーへの終了通知エラー (続行します):", error);
        alert(`サーバーへの終了通知中にエラーが発生しましたが、ブラウザの情報はクリアされます: ${error.message}`);
      }
    }
    
    clearSessionLocalStorage();
    endSessionModal.hide();
    window.location.href = '/'; 
  }

  // ★★★ セッション中断処理 ★★★
  pauseSessionBtn.addEventListener("click", pauseSession);
  
  async function pauseSession() {
    sessionIntentionallyEnding = true; 
    
    if (recording) {
      await rtc.stop();
      clearInterval(timerId);
    }

    // ★アラートを削除し、コンソールログのみにする
    console.log("セッションを中断し、ホーム画面に戻ります。");
    // 中断時は、サーバーへの通知なし、ローカルストレージのクリアもなし。
    //window.location.href = '/';
    location.replace('/');
  }
  // ★★★ 中断処理ここまで ★★★
  
  // ★★★ セッション情報破棄関数 (削除されたか確認できるようにログを追加) ★★★
  function clearSessionLocalStorage() {
    const keysToRemove = [
      'interview_material_id',
      'interview_session_id',
      'interview_current_node_id',
      'interview_uncleared_node_ids',
      'interview_next_question',
      'interview_consec_fail_count',
      'interview_session_history',
      'socratic_stage',
      'interview_completed'
    ];
    
    console.log("Attempting to clear the following local storage keys:");
    keysToRemove.forEach(key => {
      localStorage.removeItem(key);
      console.log(`- Removed: ${key}`);
    });
    console.log("Local storage clearing sequence completed.");
  }
  
  // ★★★ 最終手段のロジック: ナビゲーションバーのリンククリックをトラップし、確認後に強制クリア/遷移を実行 ★★★
  
  const navContainer = document.querySelector('.navbar-custom'); // base.htmlのカスタムナビゲーション全体
  
  if (navContainer) {
      navContainer.addEventListener('click', (e) => {
          // クリックされた要素が a.navbar-brand または a.nav-link であるかを確認
          const clickedLink = e.target.closest('a.navbar-brand, a.nav-link');
          
          if (clickedLink) {
              // 意図的な操作（ログアウト、中断）として処理しないリンクを定義
              const isIntendedAction = 
                  (clickedLink.id === 'navbarDropdown') ||
                  (clickedLink.getAttribute('href')?.includes('/logout')) ||
                  (clickedLink.getAttribute('href')?.includes('/profile')) ||
                  (clickedLink.getAttribute('href')?.includes('/register')) ||
                  (clickedLink.getAttribute('href') === '#'); 

              // セッション完了済み、または意図的なアクションでない場合、かつセッション中断中ではない場合
              if (!isIntendedAction && !sessionIntentionallyEnding && !interviewCompleted) {
                  
                  // 1. リンクのデフォルト動作（ページ遷移）を停止
                  e.preventDefault(); 
                  
                  // 2. ユーザーに確認を求める (最も確実なブロック)
                  const confirmMessage = "セッション中断ボタンを使用せずに移動すると、現在の進捗はすべて破棄されます。よろしいですか？";
                  
                  if (confirm(confirmMessage)) {
                      console.warn("User confirmed unintentional navigation. FORCING local storage clear before redirect.");
                      
                      // 3. セッション情報を同期的に確実に破棄
                      clearSessionLocalStorage(); 
                      
                      // 4. sessionIntentionallyEnding を true に設定
                      sessionIntentionallyEnding = true;
                      
                      // 5. JavaScriptで手動で再開する
                      const targetUrl = clickedLink.getAttribute('href') || '/';
                      console.log(`Redirecting to: ${targetUrl}`);
                      window.location.href = targetUrl;
                  } else {
                      // キャンセルの場合、何もしない
                      console.log("Navigation cancelled by user.");
                  }
              }
          }
      });
  }
  // ★★★ 最終手段のロジックここまで ★★★

  // ★★★ 意図しない離脱を検出する処理 (タブ閉じ、URL直接入力などに対応するため残す) ★★★
  window.addEventListener('beforeunload', (e) => {
    if (!sessionIntentionallyEnding) {
      // ユーザーがタブを閉じる、URLを直接入力するなど、
      // クリックイベントでトラップできない離脱の場合に対応

      // 1. ユーザーに確認を促すダイアログを表示
      e.preventDefault(); 
      e.returnValue = 'セッション中断ボタンを使用せずに移動すると、現在の進捗はすべて破棄されます。よろしいですか？';
      
      // 2. ユーザーが「移動する」を選択した場合に備えてクリア操作も残すが、信頼性は低い
      console.log("Unintentional exit (beforeunload) detected. Attempting to clear local storage.");
      clearSessionLocalStorage();
    }
  });
  // ★★★ 意図しない離脱処理ここまで ★★★

  // --- 補助関数 ---
  function updateSendButtonState() {
    if (answerInput && sendAnswerBtn) {
      sendAnswerBtn.disabled = answerInput.value.trim().length <= 0;
    }
  }
  
  // ★セッション終了ボタンの状態更新
  function updateEndButtonState() {
    if (endSessionBtn) {
      if (interviewCompleted) {
        // セッション完了時: 有効化し、カスタムスタイルを削除、ボタンを強調する色(ここではinfo)に戻す
        endSessionBtn.disabled = false;
        endSessionBtn.classList.remove('btn-disabled-style');
        endSessionBtn.classList.add('btn-info'); // ★有効時の色を元に戻す
      } else {
        // セッション未完了時: 無効化し、カスタムスタイルを適用
        endSessionBtn.disabled = true;
        endSessionBtn.classList.add('btn-disabled-style');
        endSessionBtn.classList.remove('btn-info'); // ★カスタムスタイル適用前に有効時の色を削除
      }
    }
  }

  function updateTranscriptionStatus(status) {
    if (!transcriptionStatus) return;
    transcriptionStatus.textContent = status;
    transcriptionStatus.className = 'badge ';
    if (status.includes('録音中') || status.includes('文字起こし中')) transcriptionStatus.className += 'bg-success';
    else if (status.includes('エラー')) transcriptionStatus.className += 'bg-danger';
    else if (status.includes('完了')) transcriptionStatus.className += 'bg-primary';
    else transcriptionStatus.className += 'bg-secondary';
  }
  function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }
function appendMessage(role, text, timestamp = null, messageType = 'chat') {
    const div = document.createElement("div");
    div.className = `message ${role === 'error' ? 'system-error' : role}`; 
    const time = timestamp || new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });

    let icon = "fa-robot";
    let sender = "AI面接官";

    if (role === "user") { 
        icon = "fa-user"; 
        sender = "あなた"; 
    } else if (role === "system") { 
        icon = "fa-info-circle"; 
        sender = "システム"; 
    } else if (role === "system-error") { 
        icon = "fa-exclamation-triangle";
        sender = "システムエラー";
    }

    if (messageType === 'evaluation') {
        if (role === 'ai') {
             icon = "fa-check-circle";
             sender = "フィードバック (高評価)";
        } else if (role === 'system-error') { 
             icon = "fa-times-circle";
             sender = "フィードバック (要確認)";
        } else { 
             icon = "fa-lightbulb";
             sender = "フィードバック";
        }
    }
    
    div.innerHTML = `
      <div class="message-content">
        <strong><i class="fas ${icon} me-1"></i>${sender}:</strong>
        ${escapeHtml(text)}
      </div>
      <div class="message-time">${time}</div>
    `;
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  }

  // --- ページ初期化処理 ---
  async function initializePage() {
    // 1. 説明フェーズで保存した「状態」をブラウザから読み込む
    currentMaterialId = localStorage.getItem('interview_material_id');
    lastQuestionText = localStorage.getItem('interview_next_question');
    currentNodeId = parseInt(localStorage.getItem('interview_current_node_id'));
    const storedUnclearedIds = localStorage.getItem('interview_uncleared_node_ids');
    const storedConsecFailCount = localStorage.getItem('interview_consec_fail_count');
    const storedHistory = localStorage.getItem('interview_session_history');
    const storedSocraticStage = localStorage.getItem('socratic_stage');
    const storedCompleted = localStorage.getItem('interview_completed'); // ★追加

    // 2. 必須項目がなければホームに戻す
    if (!currentMaterialId || !lastQuestionText || !currentNodeId || !storedUnclearedIds) {
      sessionIntentionallyEnding = true;
      alert("セッション情報が見つかりません。お手数ですが、ホームからやり直してください。");
      window.location.href = '/';
      return;
    }

    // 3. 状態をグローバル変数にセット
    try {
      unclearedNodeIds = JSON.parse(storedUnclearedIds); 
      if (storedHistory) {
        sessionHistory = JSON.parse(storedHistory); 
      }
    } catch (e) {
      console.error("セッション情報の復元に失敗しました。", e);
      sessionIntentionallyEnding = true;
      clearSessionLocalStorage();
      alert("セッション情報の復元に失敗しました。ホームからやり直してください。");
      window.location.href = '/';
      return;
    }
    if (storedConsecFailCount) {
      const parsed = parseInt(storedConsecFailCount);
      consecFailCount = isNaN(parsed) ? 0 : parsed;
    }
    if (storedSocraticStage) {
      socraticStage = parseInt(storedSocraticStage);
    }
    interviewCompleted = storedCompleted === 'true'; // ★復元

    await loadQuestionHistory(lastQuestionText);
    
    updateSendButtonState();
    // ★修正箇所2: 初期化時にもボタンの状態を更新する
    updateEndButtonState(); 
    updateTranscriptionStatus("Ready");
    
    // 完了状態の場合、回答入力欄と送信ボタンを無効化
    if (interviewCompleted) {
        answerInput.disabled = true;
        sendAnswerBtn.disabled = true;
        sessionIntentionallyEnding = true;
    }
  }

  // 最初の質問を表示
  async function loadQuestionHistory(firstQuestion) {
    setTimeout(() => {
        // 完了状態の場合は質問を表示しない
        if (!interviewCompleted) {
            appendMessage("ai", firstQuestion);
        } else {
            // 完了状態から復帰した場合のメッセージ
            appendMessage("ai", "セッションは既に完了しています。お疲れ様でした！");
        }
    }, 1500); // 少し待って最初の質問を表示
  }

  // --- ページの初期化処理を実行 ---
  initializePage();
});