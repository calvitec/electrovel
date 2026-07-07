from flask import Flask, jsonify, render_template, request, send_from_directory
from datetime import datetime
import os
import traceback

from config import Config
from routes.shop import shop_bp
from routes.api import api_bp
from routes.admin import admin_bp
from utils.data import load_orders, load_products, load_bundles, sync_products_from_supabase, sync_pending_data_if_possible

app = Flask(__name__)
application = app
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.permanent_session_lifetime = Config.PERMANENT_SESSION_LIFETIME
app.template_folder = 'templates'

# ===== STATIC FOLDER CONFIGURATION - FIXED =====
# Use absolute path for static folder
STATIC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app.static_folder = STATIC_FOLDER
app.static_url_path = '/static'

# Also set in config for other parts
Config.STATIC_FOLDER = STATIC_FOLDER

# Create upload folder
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# ===== VERCELL STATIC FILE SERVING =====
# If on Vercel, ensure static files are served correctly
if Config.IS_VERCEL:
    @app.route('/static/<path:filename>')
    def serve_static(filename):
        """Serve static files on Vercel"""
        return send_from_directory(app.static_folder, filename)

# ===== TEMPLATE FILTERS =====
@app.template_filter('format_number')
def format_number_filter(value):
    try:
        if value is None:
            return '0'
        return f"{int(float(value)):,}"
    except (ValueError, TypeError):
        return '0'

# ===== ERROR HANDLERS =====
@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/admin/') or request.path.startswith('/api/'):
        return jsonify({'error': 'Not found', 'message': 'The requested endpoint does not exist'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    print(f'Server error: {error}')
    traceback.print_exc()
    if request.path.startswith('/admin/') or request.path.startswith('/api/'):
        return jsonify({'error': 'Server error', 'message': str(error)}), 500
    return render_template('500.html'), 500

# ===== REGISTER BLUEPRINTS =====
app.register_blueprint(shop_bp)
app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)

# ===== BEFORE REQUEST =====
@app.before_request
def maybe_sync_pending_orders():
    if request.path.startswith('/static/') or request.path.startswith('/favicon.ico'):
        return None
    sync_pending_data_if_possible()
    return None

# ===== ROUTES =====
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/debug')
def debug():
    try:
        orders = load_orders()
        products = load_products()
        bundles = load_bundles()
        return jsonify({
            'orders_count': len(orders),
            'products_count': len(products),
            'bundles_count': len(bundles),
            'sample_order': orders[0] if orders else None,
            'sample_product': products[0] if products else None,
            'is_vercel': Config.IS_VERCEL,
            'static_folder': app.static_folder,
            'template_folder': app.template_folder,
        })
    except Exception as exc:
        return jsonify({'error': str(exc)})

@app.route('/load-sample-data', methods=['GET', 'POST'])
def load_sample_data():
    try:
        sample_products = [
            {
                'id': 'iphone_15',
                'name': 'iPhone 15 Pro Max',
                'price': 245000.0,
                'cost_price': 180000.0,
                'category': 'Phones',
                'description': 'Latest Apple flagship with A17 Pro chip',
                'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
                'stock': 15,
                'rating': 4.9,
                'reviews': 245,
                'badge': 'Best Seller',
            },
            {
                'id': 'macbook_pro',
                'name': 'MacBook Pro 16"',
                'price': 450000.0,
                'cost_price': 350000.0,
                'category': 'Laptops',
                'description': 'Professional laptop with M3 Max chip',
                'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
                'stock': 8,
                'rating': 4.8,
                'reviews': 156,
                'badge': 'New',
            },
            {
                'id': 'airpods_pro',
                'name': 'AirPods Pro 2',
                'price': 35000.0,
                'cost_price': 22000.0,
                'category': 'Accessories',
                'description': 'Premium wireless earbuds with ANC',
                'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
                'stock': 25,
                'rating': 4.7,
                'reviews': 389,
                'badge': 'Trending',
            },
            {
                'id': 'samsung_s24',
                'name': 'Samsung Galaxy S24 Ultra',
                'price': 225000.0,
                'cost_price': 115000.0,
                'category': 'Phones',
                'description': 'Flagship Android phone with advanced camera',
                'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
                'stock': 23,
                'rating': 4.6,
                'reviews': 234,
            },
            {
                'id': 'ipad_pro',
                'name': 'iPad Pro 12.9"',
                'price': 185000.0,
                'cost_price': 140000.0,
                'category': 'Tablets',
                'description': 'Powerful tablet with M2 chip',
                'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
                'stock': 12,
                'rating': 4.7,
                'reviews': 198,
                'badge': 'New',
            },
            {
                'id': 'hp_spectre',
                'name': 'HP Spectre x360',
                'price': 125000.0,
                'cost_price': 90000.0,
                'category': 'Laptops',
                'description': 'Convertible premium laptop',
                'image': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500',
                'stock': 18,
                'rating': 4.5,
                'reviews': 112,
            },
            {
                'id': 'watch_9',
                'name': 'Apple Watch Series 9',
                'price': 62000.0,
                'cost_price': 45000.0,
                'category': 'Wearables',
                'description': 'Smartwatch with fitness tracking',
                'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
                'stock': 26,
                'rating': 4.8,
                'reviews': 173,
            },
            {
                'id': 'usb_c_cable',
                'name': 'USB-C Fast Charging Cable',
                'price': 1200.0,
                'cost_price': 700.0,
                'category': 'Accessories',
                'description': 'Fast charging cable',
                'image': 'https://images.unsplash.com/photo-1583394838336-acd977736f90?w=500',
                'stock': 98,
                'rating': 4.4,
                'reviews': 67,
            },
            {
                'id': 'dell_xps',
                'name': 'Dell XPS 15',
                'price': 165000.0,
                'cost_price': 120000.0,
                'category': 'Laptops',
                'description': 'Thin and powerful productivity laptop',
                'image': 'https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500',
                'stock': 4,
                'rating': 4.6,
                'reviews': 99,
            },
            {
                'id': 'power_bank',
                'name': 'Anker 20000mAh Power Bank',
                'price': 8500.0,
                'cost_price': 5000.0,
                'category': 'Accessories',
                'description': 'Portable charger for travel',
                'image': 'https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500',
                'stock': 57,
                'rating': 4.7,
                'reviews': 88,
            },
            {
                'id': 'buds_2',
                'name': 'Samsung Galaxy Buds 2',
                'price': 18000.0,
                'cost_price': 12000.0,
                'category': 'Audio',
                'description': 'Noise-cancelling earbuds',
                'image': 'https://images.unsplash.com/photo-1606225457115-9b0de873c5e1?w=500',
                'stock': 45,
                'rating': 4.5,
                'reviews': 74,
            },
        ]

        import requests
        added = 0
        errors = []
        for product in sample_products:
            try:
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/products",
                    headers=Config.SUPABASE_HEADERS,
                    json=product,
                    timeout=5,
                )
                if response.status_code in [200, 201]:
                    added += 1
                else:
                    errors.append(f"{product['name']}: {response.status_code}")
            except Exception as exc:
                errors.append(f"{product['name']}: {str(exc)}")
        
        if added > 0:
            sync_products_from_supabase()

        return jsonify({'success': True, 'added': added, 'total': len(sample_products), 'errors': errors, 'message': f'Loaded {added}/{len(sample_products)} sample products'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

# ===== STATIC FILE CHECK ROUTE =====
@app.route('/static-check')
def static_check():
    """Debug route to check if static files are accessible"""
    static_path = app.static_folder
    css_path = os.path.join(static_path, 'css', 'admin.css')
    js_path = os.path.join(static_path, 'js', 'admin.js')
    
    return jsonify({
        'static_folder': static_path,
        'static_exists': os.path.exists(static_path),
        'css_exists': os.path.exists(css_path),
        'js_exists': os.path.exists(js_path),
        'is_vercel': Config.IS_VERCEL,
        'static_url_path': app.static_url_path,
    })

if __name__ == '__main__':
    print('\n' + '=' * 60)
    print('📱 PRICE POINT - Premium Electronics Shop')
    print('=' * 60)
    print(f"🌍 Environment: {'Vercel' if Config.IS_VERCEL else 'Local'}")
    print(f"📁 Static folder: {app.static_folder}")
    print(f"📁 Template folder: {app.template_folder}")
    print(f"\n📊 Products: {len(load_products())}")
    print(f"📊 Orders: {len(load_orders())}")
    print('=' * 60)
    print('\n🚀 Starting server...')
    print('📍 http://localhost:5000')
    print('🔑 Login: admin / electronics2026')
    print('=' * 60)
    app.run(debug=not Config.IS_VERCEL, host='0.0.0.0', port=5000)
