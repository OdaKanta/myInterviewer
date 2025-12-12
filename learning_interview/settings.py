"""
Django settings for learning_interview project.
"""

import os
from pathlib import Path
import environ
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key-here')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'ec2-56-155-45-112.ap-northeast-3.compute.amazonaws.com', # あなたのパブリックDNS
    '56.155.45.112' # あなたのパブリックIP (またはそれに対応するIP)
]

# Login settings
LOGIN_URL = '/'  # トップページ（ログインページ）
LOGIN_REDIRECT_URL = '/dashboard/'  # ログイン後はダッシュボード
LOGOUT_REDIRECT_URL = '/'  # ログアウト後はトップページ（ログインページ）

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'knowledge_tree',
    'interview_session',
    'question_engine',
    'frontend',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'learning_interview.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'learning_interview.wsgi.application'
ASGI_APPLICATION = 'learning_interview.asgi.application'

# Database
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',  # SQLite 用のエンジン
#         'NAME': BASE_DIR / 'db.sqlite3',         # データベースファイルのパス
#     }
# }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'myinterviewer'),
        'USER': os.environ.get('POSTGRES_USER', 'myuser'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'mypassword'),
        'HOST': 'db',  # docker-compose の service 名
        'PORT': 5432,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    BASE_DIR / 'static_dirs',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# OpenAI API settings
env = environ.Env()
environ.Env.read_env()  # .env を読み込む
OPENAI_API_KEY = env("OPENAI_API_KEY")
#OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Chroma DB settings
CHROMA_DB_PATH = BASE_DIR / 'chroma_db'

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True  # Only for development

# Channels settings - 現在未使用（OpenAI Realtime API直接接続のため）
# CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels_redis.core.RedisChannelLayer',
#         'CONFIG': {
#             "hosts": [('127.0.0.1', 6379)],
#         },
#     },
# }

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# Interview settings
INTERVIEW_CONFIG = {
    'MAX_QUESTION_TIME': 300,  # 5 minutes
    'MIN_EXPLANATION_LENGTH': 50,
    'SOCRATIC_DEPTH_LEVELS': 8,
    'AUDIO_CHUNK_SIZE': 1024,
    'SUPPORTED_AUDIO_FORMATS': ['wav', 'mp3', 'ogg'],
}

# Celery設定
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Tokyo'

VISION_MODEL = "gpt-4o-2024-11-20"