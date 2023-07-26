from chatbot.settings.base import *

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'django.log',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'WARNING',
    },
}

DEBUG = False
CORS_ALLOWED_ORIGINS = [URL]
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS").split(',')
