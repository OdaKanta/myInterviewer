# 学習者理解インタビューシステム

## 概要
本システムは、学習者が口頭で講義内容を説明し、それをLLMがソクラテス式に深掘り質問することで理解度を可視化する学習支援システムです。

## 機能
- PDFからの知識ツリー自動生成
- 音声入力による学習内容説明
- LLMによるソクラテス式質問生成
- リアルタイム理解度評価・可視化
- WebSocketによるリアルタイム通信

## 技術スタック

### 現在のアーキテクチャ（更新版）
- **バックエンド**: Django 4.2 + Django REST Framework
- **フロントエンド**: Bootstrap 5 + JavaScript（OpenAI Realtime API直接接続）
- **音声処理**: OpenAI Realtime API（ブラウザ → OpenAI直接）
- **非同期処理**: Celery 5.3.4 + Redis 5.0.1
- **AI/ML**: OpenAI API 1.100.2, Sentence Transformers 2.7.0
- **ベクトル検索**: ChromaDB 0.4.15
- **データベース**: SQLite（開発用）/ PostgreSQL（本番用）
- **プロトコル**: HTTP/1.1, HTTP/2（WebSocket未使用）

### レガシー構成（参考）
- バックエンド: Django 4.2, Django REST Framework
- フロントエンド: Bootstrap 5, JavaScript
- AI/ML: OpenAI API, Sentence Transformers
- データベース: SQLite (開発用)
- リアルタイム通信: Django Channels
- ベクトル検索: ChromaDB
- 非同期処理: Celery + Redis
- タスクキュー: Redis

## セットアップ

### 前提条件
- Python 3.11+
- Redis Server
- OpenAI API キー

### 1. 環境構築
```bash
# 仮想環境作成・有効化
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt

# Redis サーバーのインストール (Ubuntu/Debian)
sudo apt update && sudo apt install -y redis-server
```

### 2. 環境変数設定
```bash
# .envファイルを作成
cp .env.example .env

# .envファイルを編集してOpenAI API キーを設定
OPENAI_API_KEY=your-actual-api-key-here
```

### 3. データベース初期化
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 4. システム起動

システムは以下の順序で起動してください：

#### 開発環境での起動方法

##### ステップ1: Redisサーバー起動
```bash
# Redisサーバーをバックグラウンドで起動
redis-server --daemonize yes

# 接続確認
redis-cli ping  # PONGが返ってくれば正常
```

##### ステップ2: Celeryワーカー起動
```bash
# 仮想環境を有効化
source venv/bin/activate

# Celeryワーカーを起動
nohup celery -A learning_interview worker --loglevel=info > logs/celery_worker.log 2>&1 &
```

##### ステップ3A: Django開発サーバー起動（開発用）
```bash
# Django開発サーバーを起動（WSGI）
python manage.py runserver 0.0.0.0:8000
```

##### ステップ3B: Daphne ASGIサーバー起動（本番推奨）
```bash
# DaphneでASGIアプリケーションを起動（WebSocket対応）
daphne -b 0.0.0.0 -p 8000 learning_interview.asgi:application

# または詳細ログ付きで起動
daphne -b 0.0.0.0 -p 8000 --verbosity 2 learning_interview.asgi:application
```

#### 本番環境での起動方法

##### Daphneを使用した本番デプロイ
```bash
# 仮想環境有効化
source venv/bin/activate

# 静的ファイル収集
python manage.py collectstatic --noinput

# Daphneでの本番起動（systemdサービス推奨）
daphne -b 0.0.0.0 -p 8000 learning_interview.asgi:application
```

##### systemdサービス設定例
```ini
# /etc/systemd/system/learning-interview.service
[Unit]
Description=Learning Interview ASGI Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/myInterviewer
Environment=PATH=/path/to/myInterviewer/venv/bin
ExecStart=/path/to/myInterviewer/venv/bin/daphne -b 0.0.0.0 -p 8000 learning_interview.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

**Celeryワーカーの役割:**
- PDF教材の処理（テキスト抽出、埋め込み生成、知識ツリー作成）
- 重い処理を非同期でバックグラウンド実行
- Redisをメッセージブローカーとして使用

**ASGI vs WSGI:**
- **ASGI（推奨）**: WebSocket対応、非同期処理、HTTP/2サポート
- **WSGI（レガシー）**: HTTP/1.1のみ、WebSocket非対応

#### レガシー起動方法（参考）
```bash
# 従来のDjango開発サーバー（WebSocket制限あり）
python manage.py runserver 0.0.0.0:8000
```

### 5. アクセス先
- **アプリケーション**: http://localhost:8000/
- **管理画面**: http://localhost:8000/admin/

## 使用方法

### 1. 教材アップロード
1. ホームページで「新しい教材をアップロード」をクリック
2. PDFファイルとタイトルを入力してアップロード
3. **Celeryワーカーがバックグラウンドで知識ツリーを生成**
4. 処理完了まで他の操作を継続可能

### 2. インタビューセッション開始
1. 処理済みの教材で「インタビュー開始」をクリック
2. 学習内容を音声またはテキストで説明
3. 「質問フェーズへ」でソクラテス式質問開始

### 3. 質問回答
1. LLMが生成した質問に回答
2. 理解度がリアルタイムで評価される
3. 知識ツリーの色で理解度を可視化

## API エンドポイント

### 知識ツリー API
- `GET /api/knowledge-tree/materials/` - 教材一覧
- `POST /api/knowledge-tree/materials/{id}/process/` - 教材処理
- `GET /api/knowledge-tree/nodes/tree/` - 知識ツリー取得

### インタビューセッション API
- `POST /api/interview/sessions/` - セッション作成
- `POST /api/interview/explanations/` - 説明投稿
- `POST /api/interview/answers/` - 回答投稿

### 質問エンジン API  
- `POST /api/questions/generate/` - 次の質問生成
- `POST /api/questions/evaluate/` - 回答評価
- `GET /api/questions/progress/` - 進捗取得

## WebSocket接続

### 現在のWebSocket仕様
- **エンドポイント**: `ws://localhost:8000/ws/interview/{session_id}/`
- **プロトコル**: WebSocket over ASGI
- **認証**: Django認証ミドルウェア経由
- **接続管理**: Django Channels + Redis Channel Layer
- **対応ブラウザ**: 全モダンブラウザ（Chrome, Firefox, Safari, Edge）

### WebSocket機能
- リアルタイム質問配信
- 回答状況の即座反映
- 理解度評価のライブ更新
- セッション状態の同期
- 複数ユーザー対応（将来拡張）

### レガシー接続情報（参考）
- `ws://localhost:8000/ws/interview/{session_id}/` - インタビューセッション

## ディレクトリ構造

### 現在のプロジェクト構造
```
myInterviewer/
├── learning_interview/        # Django設定・ASGI設定
│   ├── settings.py           # Django設定
│   ├── asgi.py              # ASGI設定（WebSocket対応）
│   ├── wsgi.py              # WSGI設定（レガシー）
│   ├── celery.py            # Celery設定
│   └── urls.py              # URLルーティング
├── knowledge_tree/           # 知識ツリー管理
│   ├── tasks.py             # Celeryタスク（PDF処理）
│   ├── services.py          # 教材処理サービス
│   └── models.py            # データモデル
├── interview_session/        # インタビューセッション管理
│   ├── consumers.py         # WebSocketコンシューマー（ASGI）
│   ├── routing.py           # WebSocketルーティング
│   ├── models.py            # セッションモデル
│   └── serializers.py       # API シリアライザー
├── question_engine/         # 質問生成・評価エンジン
│   ├── services.py          # AI処理サービス
│   └── views.py             # REST API エンドポイント
├── frontend/               # フロントエンドビュー
│   └── views.py           # テンプレートビュー
├── templates/             # HTMLテンプレート
├── static/               # 静的ファイル（JS/CSS）
├── media/               # アップロードファイル
├── venv/               # Python仮想環境
├── requirements.txt     # 依存関係（Channels, Daphne含む）
├── setup.sh            # 初期セットアップスクリプト
└── manage_services.sh  # サービス管理スクリプト（予定）
```

### レガシー構造（参考）
```
myInterviewer/
├── learning_interview/        # Django設定
│   ├── settings.py           # Django設定
│   ├── celery.py            # Celery設定
│   └── urls.py              # URLルーティング
├── knowledge_tree/           # 知識ツリー管理
│   ├── tasks.py             # Celeryタスク（PDF処理）
│   └── services.py          # 教材処理サービス
├── interview_session/        # インタビューセッション
├── question_engine/         # 質問生成・評価
├── frontend/               # フロントエンドビュー
├── templates/             # HTMLテンプレート
├── static/               # 静的ファイル
├── media/               # アップロードファイル
└── requirements.txt     # 依存関係（Celery, Redis含む）
```

## 主要コンポーネント

### 現在のアーキテクチャコンポーネント

#### ASGI アプリケーション層
- **Django ASGI Handler**: HTTP リクエスト処理
- **WebSocket Consumer**: リアルタイム通信管理
- **Protocol Router**: HTTP/WebSocket プロトコル振り分け
- **Authentication Middleware**: WebSocket認証

#### WebSocket リアルタイム通信
- **InterviewConsumer**: インタビューセッション管理
- **Channel Layers**: Redis経由のメッセージング
- **Group Management**: セッション別グループ通信
- **Real-time Updates**: 理解度・進捗のライブ更新

#### 非同期処理システム
- **Celery**: バックグラウンドタスク処理
- **Redis**: メッセージブローカー・タスクキュー・Channel Layer
- **process_material_task**: PDF処理の非同期タスク

#### AI/ML コンポーネント
- **PDFProcessor**: PDFからテキスト抽出、チャンク化と埋め込みベクトル生成
- **KnowledgeTreeGenerator**: LLMによる階層的知識ツリー生成
- **SocraticQuestionGenerator**: ソクラテス式質問の自動生成、コンテキスト考慮した質問タイプ選択
- **AnswerEvaluator**: 回答の理解度評価、次のアクション判定
- **ExplanationAnalyzer**: 説明からトピック抽出、知識ノードとのマッピング

#### データ永続化
- **Django ORM**: データベース抽象化
- **SQLite**: 開発環境データストレージ
- **PostgreSQL**: 本番環境推奨データベース
- **ChromaDB**: ベクトルデータベース（埋め込み検索）

### レガシーコンポーネント（参考）

#### 非同期処理システム
- **Celery**: バックグラウンドタスク処理
- **Redis**: メッセージブローカー・タスクキュー
- **process_material_task**: PDF処理の非同期タスク

#### PDFProcessor
- PDFからテキスト抽出
- チャンク化と埋め込みベクトル生成

#### KnowledgeTreeGenerator
- LLMによる階層的知識ツリー生成

#### SocraticQuestionGenerator
- ソクラテス式質問の自動生成
- コンテキスト考慮した質問タイプ選択

#### AnswerEvaluator
- 回答の理解度評価
- 次のアクション判定

#### ExplanationAnalyzer
- 説明からトピック抽出
- 知識ノードとのマッピング

## トラブルシューティング

### ASGI/WebSocket関連

#### WebSocket接続エラー
```bash
# Daphneが正しく起動しているか確認
ps aux | grep daphne

# ASGIアプリケーションの設定確認
python -c "from learning_interview.asgi import application; print('ASGI OK')"

# WebSocketルーティング確認
python manage.py shell -c "from interview_session.routing import websocket_urlpatterns; print(websocket_urlpatterns)"
```

#### Channels Layer接続エラー
```bash
# Redis接続確認
redis-cli ping

# Channels設定確認
python manage.py shell -c "from channels.layers import get_channel_layer; import asyncio; asyncio.run(get_channel_layer().send('test', {'type': 'test.message'}))"
```

### Celery/Redis関連

#### Celeryワーカーが起動しない
```bash
# Redis接続確認
redis-cli ping

# Celery設定確認  
source venv/bin/activate
celery -A learning_interview inspect active
```

#### 教材処理が進まない
```bash
# タスクキューの確認
redis-cli llen celery

# ワーカーログの確認
celery -A learning_interview events

# Celeryワーカーの再起動
pkill -f celery
nohup celery -A learning_interview worker --loglevel=info > logs/celery_worker.log 2>&1 &
```

### サーバー関連

#### Daphne起動エラー
```bash
# ポート使用状況確認
lsof -i :8000

# Daphneの詳細ログで起動
daphne -b 0.0.0.0 -p 8000 --verbosity 2 learning_interview.asgi:application

# 設定ファイル確認
python manage.py check --deploy
```

#### 静的ファイル配信問題
```bash
# 静的ファイル再収集
python manage.py collectstatic --clear --noinput

# 開発環境での静的ファイル確認
python manage.py findstatic admin/css/base.css
```

### レガシートラブルシューティング（参考）

#### Celeryワーカーが起動しない
```bash
# Redis接続確認
redis-cli ping

# Celery設定確認  
celery -A learning_interview inspect active
```

#### 教材処理が進まない
```bash
# タスクキューの確認
redis-cli llen celery

# ワーカーログの確認
celery -A learning_interview events
```

#### Redis接続エラー
```bash
# Redisサーバー起動確認
redis-cli ping

# Redisプロセス確認
ps aux | grep redis-server
```

## 今後の拡張

### 短期計画（現在のASGI基盤活用）
- [ ] **WebSocket機能強化**: 複数ユーザー同時接続対応
- [ ] **リアルタイム協調**: 複数学習者での議論セッション
- [ ] **プッシュ通知**: ブラウザ通知API連携
- [ ] **モバイル対応**: PWA化とレスポンシブ改善

### 中期計画（スケーラビリティ向上）
- [ ] **マイクロサービス化**: サービス分離とAPI Gateway導入
- [ ] **Kubernetes対応**: コンテナオーケストレーション
- [ ] **CDN統合**: 静的ファイル配信最適化
- [ ] **監視・ログ**: Prometheus + Grafana導入

### 長期計画（高度なAI機能）
- [ ] **音声合成**: リアルタイム質問読み上げ
- [ ] **感情分析**: 学習者の理解状況感情認識
- [ ] **適応学習**: 個人最適化されたカリキュラム
- [ ] **VR/AR対応**: 没入型学習体験

### インフラ・運用改善
- [ ] **CI/CD パイプライン**: 自動テスト・デプロイ
- [ ] **A/Bテスト**: 機能改善データ収集
- [ ] **セキュリティ**: OAuth2/OIDC認証導入
- [ ] **パフォーマンス**: データベースクエリ最適化

### レガシー拡張計画（参考）
- [ ] 複数ユーザー対応
- [ ] より詳細な学習分析
- [ ] 音声合成による質問読み上げ
- [ ] モバイルアプリ対応
- [ ] 学習履歴の長期保存

## ライセンス
MIT License

## クイックスタート

### 現在推奨の起動方法
```bash
# Redis起動
redis-server --daemonize yes

# Celeryワーカー起動（バックグラウンド）
source venv/bin/activate
nohup celery -A learning_interview worker --loglevel=info > logs/celery_worker.log 2>&1 &

# Daphne ASGI サーバー起動（WebSocket対応）
daphne -b 0.0.0.0 -p 8000 learning_interview.asgi:application
```

### レガシー起動方法（参考）
```bash
# Redis起動
redis-server --daemonize yes

# Celeryワーカー起動
pkill -f celery
nohup celery -A learning_interview worker --loglevel=info > logs/celery_worker.log 2>&1 &

# Django開発サーバー起動（WebSocket制限あり）
python manage.py runserver 0.0.0.0:8000
```


アーカイブ
/mnt# cd /mnt && tar -czf myInterviewer_$(date +%Y%m%d_%H%M%S).tar.gz --exclude='myInterviewer/venv' --exclude='myInterviewer/media' --exclude='myInterviewer/__pycache__' --exclude='*/__pycache__' --exclude='*.pyc' myInterviewer/