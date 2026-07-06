import os
import uuid
import json
from datetime import datetime
import requests
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from config import Config

# =============================================
# APPLICATION INITIALIZATION (Crucial for Vercel)
# =============================================
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.environ.get("SECRET_KEY", "electronics-2026-fallback-key")

# Register Blueprints
from routes.admin import admin_bp
app.register_blueprint(admin_bp)

# =============================================
# MEMORY CACHE & IN-MEMORY STORAGE
# =============================================
ORDERS_CACHE = []
PRODUCTS_CACHE = []
BUNDLES_CACHE = []
GLOBAL_CART = {}

# =============================================
# HELPER FUNCTIONS / DATA UTILITIES
# =============================================
def load_products():
    global PRODUCTS_CACHE
    if PRODUCTS_CACHE:
        return PRODUCTS_CACHE
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/products?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            PRODUCTS_CACHE = response.json()
            return PRODUCTS_CACHE
    except Exception as exc:
        print(f"Error loading products: {exc}")
    return []

def load_orders():
    global ORDERS_CACHE
    if ORDERS_CACHE:
        return ORDERS_CACHE
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/orders?select=*&order=created_at.desc",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            raw_orders = response.json()
            cleaned_orders = []
            for order in raw_orders:
                if isinstance(order.get('items'), str):
                    try:
                        order['items'] = json.loads(order['items'])
                    except Exception:
                        order['items'] = []
                cleaned_orders.append(order)
            ORDERS_CACHE = cleaned_orders
            return ORDERS_CACHE
    except Exception as exc:
        print(f"Error loading orders: {exc}")
    return []

def load_bundles():
    global BUNDLES_CACHE
    if BUNDLES_CACHE:
        return BUNDLES_CACHE
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/bundles?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            BUNDLES_CACHE = response.json()
            return BUNDLES_CACHE
    except Exception as exc:
        print(f"Error loading bundles: {exc}")
    return []

def sync_products_from_supabase():
    global PRODUCTS_CACHE
    PRODUCTS_CACHE = []
    return load_products()

# =============================================
# MAIN FRONTEND STORE ROUTES
# =============================================
@app.route('/')
def index():
    products = load_products()
    bundles = load_bundles()
    featured = [p for p in products if p.get('stock', 0) > 0][:8]
    return render_template('index.html', products=featured, bundles=bundles)

@app.route('/shop')
def shop():
    products = load_products()
    category = request.args.get('category', 'all')
    search_query = request.args.get('search', '').lower()
    
    filtered_products = products
    if category != 'all':
        filtered_products = [p for p in filtered_products if p.get('category', '').lower() == category.lower()]
    if search_query:
        filtered_products = [p for p in filtered_products if search_query in p.get('name', '').lower() or search_query in p.get('description', '').lower()]
        
    categories = sorted(list(set([p.get('category', 'General') for p in products if p.get('category')])))
    return render_template('shop.html', products=filtered_products, categories=categories, selected_category=category)

@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if str(p.get('id')) == str(product_id)), None)
    if not product:
        flash("Product not found", "danger")
        return redirect(url_for('shop'))
    
    related = [p for p in products if p.get('category') == product.get('category') and str(p.get('id')) != str(product_id)][:4]
    return render_template('product_detail.html', product=product, related_products=related)

# =============================================
# CART FUNCTIONALITY
# =============================================
@app.route('/cart')
def view_cart():
    products = load_products()
    product_lookup = {str(p.get('id')): p for p in products}
    
    cart_items = []
    subtotal = 0
    for p_id, qty in GLOBAL_CART.items():
        product = product_lookup.get(str(p_id))
        if product:
            total_price = float(product.get('price', 0)) * qty
            subtotal += total_price
            cart_items.append({
                'product': product,
                'quantity': qty,
                'total_price': total_price
            })
            
    shipping = 15.0 if subtotal > 0 else 0.0
    total = subtotal + shipping
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal, shipping=shipping, total=total)

@app.route('/cart/add/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    qty = int(request.form.get('quantity', 1))
    products = load_products()
    product = next((p for p in products if str(p.get('id')) == str(product_id)), None)
    
    if product:
        stock = product.get('stock', 0)
        current_in_cart = GLOBAL_CART.get(str(product_id), 0)
        if current_in_cart + qty > stock:
            flash(f"Cannot add more items than available stock ({stock} units total)", "warning")
            return redirect(request.referrer or url_for('shop'))
            
        GLOBAL_CART[str(product_id)] = current_in_cart + qty
        flash(f"Added {product.get('name')} to cart!", "success")
    return redirect(request.referrer or url_for('shop'))

@app.route('/cart/update/<product_id>', methods=['POST'])
def update_cart(product_id):
    qty = int(request.form.get('quantity', 1))
    if qty <= 0:
        GLOBAL_CART.pop(str(product_id), None)
    else:
        GLOBAL_CART[str(product_id)] = qty
    return redirect(url_for('view_cart'))

@app.route('/cart/remove/<product_id>')
def remove_from_cart(product_id):
    GLOBAL_CART.pop(str(product_id), None)
    flash("Item removed from cart", "info")
    return redirect(url_for('view_cart'))

# =============================================
# CHECKOUT & ORDER COMPLETION
# =============================================
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not GLOBAL_CART:
        flash("Your cart is empty", "warning")
        return redirect(url_for('shop'))
        
    products = load_products()
    product_lookup = {str(p.get('id')): p for p in products}
    
    subtotal = 0
    items_ordered = []
    for p_id, qty in GLOBAL_CART.items():
        product = product_lookup.get(str(p_id))
        if product:
            price = float(product.get('price', 0))
            subtotal += price * qty
            items_ordered.append({
                'product_id': p_id,
                'name': product.get('name'),
                'price': price,
                'quantity': qty,
                'cost_price': float(product.get('cost_price', 0))
            })
            
    shipping = 15.0
    total = subtotal + shipping
    
    if request.method == 'POST':
        order_id = f"WEB-{uuid.uuid4().hex[:8].upper()}"
        order_data = {
            'order_id': order_id,
            'items': items_ordered,
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
            'status': 'pending',
            'source': 'web',
            'created_at': datetime.utcnow().isoformat(),
            'customer': {
                'name': request.form.get('name'),
                'email': request.form.get('email'),
                'phone': request.form.get('phone'),
                'address': request.form.get('address'),
                'city': request.form.get('city'),
                'zip': request.form.get('zip')
            }
        }
        
        try:
            response = requests.post(
                f"{Config.SUPABASE_URL}/rest/v1/orders",
                headers=Config.SUPABASE_HEADERS,
                json={
                    'order_id': order_id,
                    'customer': json.dumps(order_data['customer']),
                    'items': json.dumps(items_ordered),
                    'total': total,
                    'status': 'pending',
                    'source': 'web',
                    'created_at': order_data['created_at']
                },
                timeout=5
            )
            if response.status_code in [200, 201]:
                # Adjust local stocks
                for item in items_ordered:
                    p_id = item['product_id']
                    p = product_lookup.get(p_id)
                    if p:
                        new_stock = max(0, p.get('stock', 0) - item['quantity'])
                        requests.patch(
                            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{p_id}",
                            headers=Config.SUPABASE_HEADERS,
                            json={'stock': new_stock},
                            timeout=5
                        )
                
                GLOBAL_CART.clear()
                global ORDERS_CACHE, PRODUCTS_CACHE
                ORDERS_CACHE = []
                PRODUCTS_CACHE = []
                return render_template('order_success.html', order_id=order_id)
            else:
                flash(f"Failed to place order. Database error code: {response.status_code}", "danger")
        except Exception as exc:
            flash(f"Order submission error: {str(exc)}", "danger")
            
    return render_template('checkout.html', subtotal=subtotal, shipping=shipping, total=total, count=len(items_ordered))

# =============================================
# SEED SAMPLE DATA ROUTE
# =============================================
@app.route('/admin/seed-sample-products', methods=['POST'])
def seed_sample_products():
    try:
        sample_products = [
            {
                'id': '11111111-1111-1111-1111-111111111111',
                'name': 'QuantumX Wireless Headphones',
                'price': 299.99,
                'cost_price': 120.00,
                'stock': 45,
                'category': 'Audio',
                'description': 'Premium noise-canceling wireless headphones with hybrid drivers.',
                'image': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500',
                'rating': 4.8,
                'reviews': 128,
                'badge': 'Top Rated'
            },
            {
                'id': '22222222-2222-2222-2222-222222222222',
                'name': 'AeroWatch Pro Smartwatch',
                'price': 199.99,
                'cost_price': 85.00,
                'stock': 60,
                'category': 'Wearables',
                'description': 'Advanced AMOLED health tracking wristwatch with 14-day standby.',
                'image': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500',
                'rating': 4.5,
                'reviews': 84,
                'badge': 'New'
            },
            {
                'id': '33333333-3333-3333-3333-333333333333',
                'name': 'ApexMech Mechanical Keyboard',
                'price': 149.99,
                'cost_price': 60.00,
                'stock': 8,
                'category': 'Accessories',
                'description': 'Tactile hot-swappable RGB physical keys layout keyboard.',
                'image': 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=500',
                'rating': 4.9,
                'reviews': 245,
                'badge': 'Best Seller'
            }
        ]
        
        added = 0
        errors = []
        for product in sample_products:
            try:
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/products",
                    headers=Config.SUPABASE_HEADERS,
                    json=product,
                    timeout=5
                )
                if response.status_code in [200, 201]:
                    added += 1
                else:
                    errors.append(f"{product['name']}: {response.status_code}")
            except Exception as exc:
                errors.append(f"{product['name']}: {str(exc)}")
                
        if added > 0:
            sync_products_from_supabase()
            
        return jsonify({
            'success': True,
            'added': added,
            'total': len(sample_products),
            'errors': errors,
            'message': f'Loaded {added}/{len(sample_products)} sample products'
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

# =============================================
# RUN THE APP
# =============================================
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
