from flask import Flask, jsonify, render_template, request, session
from datetime import datetime
import os
import traceback

from config import Config
from routes.shop import shop_bp
from routes.api import api_bp
from routes.admin import admin_bp
from utils.data import load_orders, load_products, load_bundles, sync_products_from_supabase, sync_pending_data_if_possible

# ===== VERCEL NEEDS THIS =====
app = Flask(__name__)
application = app
# =============================

app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.permanent_session_lifetime = Config.PERMANENT_SESSION_LIFETIME
app.template_folder = 'templates'
app.static_folder = Config.STATIC_FOLDER

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


@app.template_filter('format_number')
def format_number_filter(value):
    try:
        if value is None:
            return '0'
        return f"{int(float(value)):,}"
    except (ValueError, TypeError):
        return '0'


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


app.register_blueprint(shop_bp)
app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)


@app.before_request
def maybe_sync_pending_orders():
    if request.path.startswith('/static/') or request.path.startswith('/favicon.ico'):
        return None
    sync_pending_data_if_possible()
    return None


@app.route('/')
def index():
    products = load_products()
    bundles = load_bundles()
    categories = {}
    
    for product_id, product in products.items():
        category = product.get('category', 'Uncategorized')
        if category not in categories:
            categories[category] = {
                'count': 0,
                'icon': 'fa-box'
            }
        categories[category]['count'] += 1
    
    return render_template('shop.html', 
                         all_products=products, 
                         bundles=bundles,
                         categories=categories)


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/status')
def api_status():
    try:
        orders = load_orders()
        products = load_products()
        return jsonify({
            'status': 'ok',
            'orders_count': len(orders),
            'products_count': len(products),
            'db_connected': True
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'db_connected': False
        })


@app.route('/cart')
def cart():
    cart_items = []
    total = 0
    products = load_products()
    
    cart = session.get('cart', {})
    if isinstance(cart, list):
        new_cart = {}
        for item_id in cart:
            new_cart[item_id] = new_cart.get(item_id, 0) + 1
        session['cart'] = new_cart
        session.modified = True
        cart = new_cart
    
    for product_id, quantity in cart.items():
        product = products.get(product_id)
        if product:
            price = product.get('price', 0)
            item_total = price * quantity
            cart_items.append({
                'id': product_id,
                'name': product.get('name', 'Product'),
                'price': price,
                'quantity': quantity,
                'total': item_total,
                'image': product.get('image', ''),
                'stock': product.get('stock', 0)
            })
            total += item_total
    
    return render_template('cart.html', cart_items=cart_items, total=total)


@app.route('/cart-count')
def cart_count():
    cart = session.get('cart', {})
    if isinstance(cart, list):
        return jsonify({'count': len(cart)})
    return jsonify({'count': sum(cart.values()) if cart else 0})


@app.route('/add-to-cart/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    cart = session.get('cart', {})
    if isinstance(cart, list):
        new_cart = {}
        for item_id in cart:
            new_cart[item_id] = new_cart.get(item_id, 0) + 1
        cart = new_cart
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart
    session.modified = True
    total_items = sum(cart.values()) if cart else 0
    return jsonify({'success': True, 'count': total_items})


@app.route('/update-cart', methods=['POST'])
def update_cart():
    data = request.get_json()
    cart = session.get('cart', {})
    
    if isinstance(cart, list):
        new_cart = {}
        for item_id in cart:
            new_cart[item_id] = new_cart.get(item_id, 0) + 1
        cart = new_cart
    
    for product_id, quantity in data.items():
        if quantity <= 0:
            cart.pop(product_id, None)
        else:
            cart[product_id] = quantity
    
    session['cart'] = cart
    session.modified = True
    
    total = sum(cart.values()) if cart else 0
    return jsonify({'success': True, 'count': total})


@app.route('/remove-from-cart/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    
    if isinstance(cart, list):
        new_cart = {}
        for item_id in cart:
            new_cart[item_id] = new_cart.get(item_id, 0) + 1
        cart = new_cart
    
    cart.pop(product_id, None)
    session['cart'] = cart
    session.modified = True
    
    total = sum(cart.values()) if cart else 0
    return jsonify({'success': True, 'count': total})


@app.route('/load-sample-data', methods=['GET', 'POST'])
def load_sample_data():
    try:
        sample_products = [
            {
                'id': 'iphone_16_pro_max',
                'name': 'iPhone 16 Pro Max',
                'price': 265000.0,
                'cost_price': 195000.0,
                'category': 'Phones',
                'description': 'Latest Apple flagship',
                'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
                'stock': 20,
                'rating': 4.9,
                'reviews': 312,
                'badge': 'Best Seller',
            },
            {
                'id': 'macbook_pro_m4',
                'name': 'MacBook Pro M4 16"',
                'price': 520000.0,
                'cost_price': 400000.0,
                'category': 'Laptops',
                'description': 'Professional laptop',
                'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
                'stock': 8,
                'rating': 4.9,
                'reviews': 189,
                'badge': 'Best Seller',
            },
            {
                'id': 'airpods_pro_3',
                'name': 'AirPods Pro 3',
                'price': 42000.0,
                'cost_price': 31000.0,
                'category': 'Audio',
                'description': 'Top-tier wireless earbuds',
                'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
                'stock': 35,
                'rating': 4.8,
                'reviews': 389,
                'badge': 'Best Seller',
            },
            {
                'id': 'samsung_s25_ultra',
                'name': 'Samsung Galaxy S25 Ultra',
                'price': 255000.0,
                'cost_price': 185000.0,
                'category': 'Phones',
                'description': 'Ultimate Android flagship',
                'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
                'stock': 15,
                'rating': 4.9,
                'reviews': 278,
                'badge': 'Best Seller',
            },
            {
                'id': 'ipad_pro_m4',
                'name': 'iPad Pro M4 13"',
                'price': 220000.0,
                'cost_price': 165000.0,
                'category': 'Tablets',
                'description': 'Pro tablet with M4 chip',
                'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
                'stock': 15,
                'rating': 4.9,
                'reviews': 245,
                'badge': 'Best Seller',
            }
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


if __name__ == '__main__':
    print('\n' + '=' * 60)
    print('📱 PRICE POINT - Premium Electronics Shop')
    print('=' * 60)
    print(f"🌍 Environment: {'Vercel' if Config.IS_VERCEL else 'Local'}")
    print(f"\n📊 Products: {len(load_products())}")
    print(f"📊 Orders: {len(load_orders())}")
    print('=' * 60)
    print('\n🚀 Starting server...')
    print('📍 http://localhost:5000')
    print('🔑 Login: admin / electronics2026')
    print('=' * 60)
    app.run(debug=not Config.IS_VERCEL, host='0.0.0.0', port=5000)
