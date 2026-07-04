import os
import traceback
import uuid
from datetime import datetime

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from config import Config
from utils.data import get_cart, get_sales_analytics, load_bundles, load_orders, load_products, save_order_to_supabase, update_product_stock

admin_bp = Blueprint('admin', __name__)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'electronics2026':
            session['admin_logged_in'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('admin.admin_dashboard'))
        flash('Invalid credentials', 'danger')

    return render_template('admin_login.html')


@admin_bp.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out', 'success')
    return redirect(url_for('admin.admin_login'))


@admin_bp.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Please login first', 'danger')
        return redirect(url_for('admin.admin_login'))

    try:
        products = load_products()
        orders = load_orders()
        bundles = load_bundles()
        cart = get_cart()
        analytics = get_sales_analytics()

        customer_list = {}
        pos_count = 0
        web_count = 0
        for order in orders:
            customer = order.get('customer', {})
            if isinstance(customer, str):
                try:
                    customer = __import__('json').loads(customer)
                except Exception:
                    customer = {}
            if isinstance(customer, list):
                customer = customer[0] if customer else {}
            if not isinstance(customer, dict):
                customer = {}
            source = order.get('source', 'web')
            if source == 'pos':
                pos_count += 1
            else:
                web_count += 1
            name = customer.get('name', 'Unknown') if isinstance(customer, dict) else 'Unknown'
            if name and name != 'Unknown':
                if name not in customer_list:
                    customer_list[name] = {'name': name, 'email': customer.get('email', ''), 'phone': customer.get('phone', ''), 'orders': 0, 'total_spent': 0}
                customer_list[name]['orders'] += 1
                customer_list[name]['total_spent'] += order.get('total', 0)

        customers = list(customer_list.values())
        customers.sort(key=lambda x: x['orders'], reverse=True)

        stats = {
            'total_products': len(products),
            'total_bundles': len(bundles),
            'total_cart_items': sum(cart.values()) if cart else 0,
            'low_stock': len([p for p in products if p.get('stock', 0) < 10]),
            'total_orders': len(orders),
            'pending_orders': len([o for o in orders if o.get('status') == 'pending']),
            'pos_orders': pos_count,
            'web_orders': web_count,
            'total_revenue': analytics.get('total_revenue', 0),
            'total_profit': analytics.get('total_profit', 0),
            'total_items_sold': analytics.get('total_items_sold', 0),
            'total_customers': len(customers),
            'db_mode': 'online',
        }

        return render_template('admin.html', products=products, bundles=bundles, orders=orders, customers=customers, stats=stats, pos_count=pos_count, analytics=analytics, DB_CONNECTED=True)
    except Exception as exc:
        print(f'Admin dashboard error: {exc}')
        traceback.print_exc()
        flash('Error loading admin dashboard', 'danger')
        return render_template('admin.html', products=[], bundles=[], orders=[], customers=[], pos_count=0, analytics={}, stats={
            'total_products': 0,
            'total_bundles': 0,
            'total_cart_items': 0,
            'low_stock': 0,
            'total_orders': 0,
            'pending_orders': 0,
            'pos_orders': 0,
            'web_orders': 0,
            'total_revenue': 0,
            'total_profit': 0,
            'total_items_sold': 0,
            'total_customers': 0,
            'db_mode': 'offline',
        }, DB_CONNECTED=False)


@admin_bp.route('/admin/pos')
def admin_pos():
    if not session.get('admin_logged_in'):
        flash('Please login first', 'danger')
        return redirect(url_for('admin.admin_login'))

    products = load_products()
    for product in products:
        if 'price' not in product or product['price'] is None:
            product['price'] = 0
        if 'stock' not in product or product['stock'] is None:
            product['stock'] = 0
        if 'image' not in product:
            product['image'] = ''
        if 'name' not in product:
            product['name'] = 'Product'
        if 'id' not in product:
            product['id'] = str(uuid.uuid4())

    customer_list = {}
    orders = load_orders()
    for order in orders:
        customer = order.get('customer', {})
        if isinstance(customer, str):
            try:
                customer = __import__('json').loads(customer)
            except Exception:
                customer = {}
        if isinstance(customer, list):
            customer = customer[0] if customer else {}
        if not isinstance(customer, dict):
            customer = {}
        name = customer.get('name', 'Unknown') if isinstance(customer, dict) else 'Unknown'
        if name and name != 'Unknown':
            if name not in customer_list:
                customer_list[name] = {'name': name, 'email': customer.get('email', ''), 'phone': customer.get('phone', ''), 'orders': 0, 'total_spent': 0}
            customer_list[name]['orders'] += 1
            customer_list[name]['total_spent'] += order.get('total', 0)

    customers = list(customer_list.values())
    customers.sort(key=lambda x: x['orders'], reverse=True)
    return render_template('pos.html', products=products, customers=customers, DB_CONNECTED=True)


@admin_bp.route('/admin/pos/place-order', methods=['POST'])
def admin_pos_place_order():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data or not data.get('items'):
            return jsonify({'success': False, 'message': 'No items in order'}), 400

        order_id = f'POS-{uuid.uuid4().hex[:8].upper()}'
        products = load_products()
        product_lookup = {str(p.get('id')): p for p in products}

        for item in data.get('items', []):
            product_id = str(item.get('product_id'))
            quantity = item.get('quantity', 1)
            product = product_lookup.get(product_id)
            if product:
                current_stock = product.get('stock', 0)
                if current_stock < quantity:
                    return jsonify({'success': False, 'message': f'Not enough stock for {product.get("name")}. Available: {current_stock}'}), 400
                new_stock = max(0, current_stock - quantity)
                update_product_stock(product_id, new_stock)

        order_data = {
            'order_id': order_id,
            'items': data.get('items', []),
            'subtotal': data.get('subtotal', 0),
            'shipping': data.get('shipping', 0),
            'total': data.get('total', 0),
            'status': 'confirmed',
            'source': 'pos',
            'created_at': datetime.utcnow().isoformat(),
            'customer': {
                'name': data.get('customer_name', 'Walk-in Customer'),
                'email': data.get('customer_email', 'walkin@example.com'),
                'phone': data.get('customer_phone', 'N/A'),
                'address': data.get('customer_address', 'In-store purchase'),
            },
        }

        save_result = save_order_to_supabase(order_data)
        if save_result.get('success'):
            analytics = get_sales_analytics()
            return jsonify({'success': True, 'order_id': order_id, 'message': save_result.get('message', 'Order placed successfully!'), 'analytics': analytics, 'stats': {
                'total_revenue': analytics.get('total_revenue', 0),
                'total_profit': analytics.get('total_profit', 0),
                'total_orders': analytics.get('total_orders', 0),
                'total_items_sold': analytics.get('total_items_sold', 0),
                'pos_orders_count': analytics.get('pos_orders_count', 0),
                'web_orders_count': analytics.get('web_orders_count', 0),
            }, 'queued': save_result.get('queued', False), 'synced': save_result.get('synced', False)})
        return jsonify({'success': False, 'message': save_result.get('message', 'Failed to save order')}), 500
    except Exception as exc:
        print(f'POS Order error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500


@admin_bp.route('/admin/api/analytics')
def admin_api_analytics():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(get_sales_analytics())


@admin_bp.route('/admin/api/revenue')
def admin_api_revenue():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    analytics = get_sales_analytics()
    return jsonify({'total_revenue': analytics.get('total_revenue', 0), 'total_profit': analytics.get('total_profit', 0), 'total_orders': analytics.get('total_orders', 0), 'total_items_sold': analytics.get('total_items_sold', 0)})


@admin_bp.route('/admin/upload-image', methods=['POST'])
def upload_image():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    if file and allowed_file(file.filename):
        filename = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        image_url = f"/static/uploads/{filename}"
        return jsonify({'success': True, 'url': image_url, 'message': 'Image uploaded successfully!'})
    return jsonify({'success': False, 'message': 'Invalid file type'}), 400


@admin_bp.route('/admin/products', methods=['POST'])
def admin_products():
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        product_data = {
            'id': request.form.get('id'),
            'name': request.form.get('name'),
            'price': float(request.form.get('price', 0)),
            'cost_price': float(request.form.get('cost_price', 0)) or 0,
            'image': request.form.get('image'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'rating': float(request.form.get('rating', 4.0)),
            'reviews': int(request.form.get('reviews', 0)),
            'badge': request.form.get('badge', ''),
            'stock': int(request.form.get('stock', 0)),
            'original_price': float(request.form.get('original_price', 0)) or None,
            'specs': request.form.get('specs', '').split(',') if request.form.get('specs') else [],
        }
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/products",
            headers=Config.SUPABASE_HEADERS,
            json=product_data,
            timeout=5,
        )
        if response.status_code in [200, 201]:
            return jsonify({'success': True, 'message': 'Product saved successfully!', 'product': product_data})
        return jsonify({'success': False, 'message': 'Error saving product'}), 500
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


@admin_bp.route('/admin/products/<product_id>', methods=['DELETE'])
def admin_delete_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    try:
        response = requests.delete(
            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code in [200, 204]:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to delete'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)})


@admin_bp.route('/admin/orders/<order_id>/status', methods=['POST'])
def admin_update_order_status(order_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    try:
        new_status = request.json.get('status')
        if not new_status:
            return jsonify({'success': False, 'message': 'Status required'}), 400
        response = requests.patch(
            f"{Config.SUPABASE_URL}/rest/v1/orders?order_id=eq.{order_id}",
            headers=Config.SUPABASE_HEADERS,
            json={'status': new_status},
            timeout=5,
        )
        if response.status_code in [200, 204]:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to update status'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500
