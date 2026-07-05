import os
from datetime import timedelta


class Config:
    SECRET_KEY = 'allison-electronics-secret-2026'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    IS_VERCEL = 'VERCEL' in os.environ or 'NOW' in os.environ
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

    if IS_VERCEL:
        UPLOAD_FOLDER = '/tmp/static/uploads'
        STATIC_FOLDER = '/tmp/static'
    else:
        UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'static', 'uploads')
        STATIC_FOLDER = os.path.join(PROJECT_ROOT, 'static')

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # ===== SUPABASE CONFIGURATION =====
    # Use environment variables on Vercel, fallback for local development
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://hzqrdwerkgfmfaufabjr.supabase.co')
    
    # IMPORTANT: Use your SECRET key (starts with sb_secret)
    # This key has write permissions for server-side operations
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_secret_8Jk_nZzU7_cEBspHtHV0Ew_KTxfnQ65')
    
    SUPABASE_HEADERS = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
