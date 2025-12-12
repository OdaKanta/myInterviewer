#!/bin/bash

# 学習者理解インタビューシステム セットアップスクリプト

echo "=== 学習者理解インタビューシステム セットアップ ==="

# 仮想環境の確認
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "警告: 仮想環境が有効になっていません。"
    echo "推奨: python -m venv venv && source venv/bin/activate"
fi

# 依存関係のインストール
echo "1. 依存関係をインストール中..."
pip install -r requirements.txt

# 環境変数ファイルの作成
if [ ! -f .env ]; then
    echo "2. .env ファイルを作成中..."
    cp .env.example .env
    echo "   .env ファイルが作成されました。OpenAI API キーを設定してください。"
else
    echo "2. .env ファイルは既に存在します。"
fi

# データベースマイグレーション
echo "3. データベースを初期化中..."
python manage.py makemigrations knowledge_tree
python manage.py makemigrations interview_session
python manage.py makemigrations
python manage.py migrate

# スーパーユーザー作成の確認
echo "4. 管理者ユーザーを作成しますか？ [y/N]"
read -r create_superuser
if [[ $create_superuser =~ ^[Yy]$ ]]; then
    python manage.py createsuperuser
fi

# 静的ファイルの収集
echo "5. 静的ファイルを収集中..."
python manage.py collectstatic --noinput

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "システムを起動するには以下の順序で実行してください："
echo ""
echo "1. Redisサーバーを起動:"
echo "  redis-server --daemonize yes"
echo ""
echo "2. Celeryワーカーを起動 (別ターミナル):"
echo "  celery -A learning_interview worker --loglevel=info"
echo ""
echo "3. Djangoサーバーを起動 (別ターミナル):"
echo "  python manage.py runserver 0.0.0.0:8000"
echo ""
echo "アクセスURL:"
echo "  アプリケーション: http://localhost:8000/"
echo "  管理画面: http://localhost:8000/admin/"
echo ""
echo "重要な設定:"
echo "  - .env ファイルでOpenAI API キーを設定してください"
echo "  - 教材処理はCeleryによりバックグラウンドで非同期実行されます"
echo "  - Redisはタスクキューとして使用されます"
