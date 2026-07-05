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

    # ===== CRITICAL FIX =====
    # Use environment variables for Supabase keys (especially on Vercel)
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://hzqrdwerkgfmfaufabjr.supabase.co')
    
    # IMPORTANT: Use SERVICE ROLE KEY, NOT publishable key!
    # Get from: Supabase Dashboard → Settings → API → Service Role Key
    # It starts with: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_tnBOmCO7EFfIoXfNjEH_Tg_D7WX-zld')
    
    SUPABASE_HEADERS = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

    DATA_FILE = os.path.join(PROJECT_ROOT, 'offline_data.json')
