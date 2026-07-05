import os
import traceback
import uuid
from datetime import datetime, timedelta

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

        items = data.get('items', [])
        calculated_subtotal = 0
        items_with_cost = []

        for item in items:
            product_id = str(item.get('product_id'))
            quantity = item.get('quantity', 1)
            price = item.get('price', 0)
            
            # Calculate subtotal from items
            calculated_subtotal += price * quantity
            
            # Get product details for cost price
            product = product_lookup.get(product_id)
            cost_price = product.get('cost_price', 0) if product else 0
            
            # Add cost price to item for profit calculation
            item_with_cost = item.copy()
            item_with_cost['cost_price'] = cost_price
            items_with_cost.append(item_with_cost)
            
            # Update stock
            if product:
                current_stock = product.get('stock', 0)
                if current_stock < quantity:
                    return jsonify({
                        'success': False, 
                        'message': f'Not enough stock for {product.get("name")}. Available: {current_stock}'
                    }), 400
                new_stock = max(0, current_stock - quantity)
                update_product_stock(product_id, new_stock)

        # Use calculated values
        subtotal = calculated_subtotal if calculated_subtotal > 0 else data.get('subtotal', 0)
        shipping = data.get('shipping', 0)
        total = subtotal + shipping

        order_data = {
            'order_id': order_id,
            'items': items_with_cost,  # Store items with cost price
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
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

        # Save order to database
        save_result = save_order_to_supabase(order_data)
        
        if save_result.get('success'):
            # ===== CRITICAL: Force reload orders from Supabase =====
            all_orders = load_orders()
            
            # Calculate analytics manually for accurate results
            total_revenue = sum(float(order.get('total', 0) or 0) for order in all_orders)
            
            # Calculate total profit
            total_profit = 0
            total_items_sold = 0
            pos_orders_count = 0
            web_orders_count = 0
            
            for order in all_orders:
                # Count order sources
                if order.get('source') == 'pos':
                    pos_orders_count += 1
                else:
                    web_orders_count += 1
                
                # Calculate items sold and profit
                for item in order.get('items', []):
                    quantity = item.get('quantity', 1)
                    total_items_sold += quantity
                    
                    # Calculate profit if cost price is available
                    price = item.get('price', 0)
                    cost_price = item.get('cost_price', 0)
                    if cost_price > 0:
                        total_profit += (price - cost_price) * quantity
                    elif price > 0:
                        # If no cost price, assume 30% profit margin
                        total_profit += price * quantity * 0.3
            
            # Create analytics object with accurate data
            analytics = {
                'total_revenue': total_revenue,
                'total_profit': total_profit,
                'total_orders': len(all_orders),
                'total_items_sold': total_items_sold,
                'pos_orders_count': pos_orders_count,
                'web_orders_count': web_orders_count,
                'product_sales': {},
                'category_sales': {}
            }
            
            print(f"✅ Order placed: {order_id}")
            print(f"📊 Total revenue: {total_revenue}")
            print(f"📊 Total orders: {len(all_orders)}")
            
            return jsonify({
                'success': True, 
                'order_id': order_id, 
                'message': 'Order placed successfully!', 
                'analytics': analytics, 
                'stats': {
                    'total_revenue': total_revenue,
                    'total_profit': total_profit,
                    'total_orders': len(all_orders),
                    'total_items_sold': total_items_sold,
                    'pos_orders_count': pos_orders_count,
                    'web_orders_count': web_orders_count,
                }, 
                'queued': save_result.get('queued', False), 
                'synced': save_result.get('synced', False)
            })
        else:
            return jsonify({
                'success': False, 
                'message': save_result.get('message', 'Failed to save order')
            }), 500
            
    except Exception as exc:
        print(f'POS Order error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500


@admin_bp.route('/admin/api/analytics')
def admin_api_analytics():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Force refresh analytics
    orders = load_orders()
    analytics = calculate_analytics_from_orders(orders)
    return jsonify(analytics)


@admin_bp.route('/admin/api/revenue')
def admin_api_revenue():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        print("🔍 Fetching revenue data...")

        # Use load_orders() - the shared source that includes queued orders
        orders = load_orders()

        print(f"📊 Revenue API: Found {len(orders)} orders")

        if not orders:
            return jsonify({
                "total_revenue": 0,
                "total_orders": 0,
                "today_revenue": 0,
                "today_orders": 0,
                "yesterday_revenue": 0,
                "month_revenue": 0,
                "month_orders": 0,
                "last_month_revenue": 0,
                "today_growth_pct": 0,
                "month_growth_pct": 0,
                "total_profit": 0,
                "total_items_sold": 0
            })

        now = datetime.utcnow()
        today = now.date()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)

        total_revenue = 0
        total_profit = 0
        total_items_sold = 0
        today_revenue = 0
        today_orders = 0
        yesterday_revenue = 0
        month_revenue = 0
        month_orders = 0
        last_month_revenue = 0

        for order in orders:
            total = order.get('total', 0)
            if isinstance(total, str):
                try:
                    total = float(total.replace(',', ''))
                except:
                    total = 0
            total = float(total or 0)
            
            if total == 0:
                continue

            total_revenue += total

            # Calculate profit
            for item in order.get('items', []):
                quantity = item.get('quantity', 1)
                total_items_sold += quantity
                
                price = item.get('price', 0)
                cost_price = item.get('cost_price', 0)
                if cost_price > 0:
                    total_profit += (price - cost_price) * quantity
                elif price > 0:
                    total_profit += price * quantity * 0.3

            created_at = order.get('created_at', '')
            if not created_at:
                continue

            try:
                if isinstance(created_at, datetime):
                    order_date = created_at.date()
                elif isinstance(created_at, str):
                    if ' ' in created_at and '.' in created_at:
                        order_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f').date()
                    elif ' ' in created_at:
                        order_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S').date()
                    elif 'T' in created_at:
                        clean = created_at.replace('Z', '').replace('+00:00', '')
                        order_date = datetime.fromisoformat(clean).date() if '.' in clean else datetime.strptime(clean, '%Y-%m-%dT%H:%M:%S').date()
                    else:
                        order_date = datetime.strptime(created_at, '%Y-%m-%d').date()
                else:
                    continue
            except Exception as e:
                print(f"⚠️ Date parse error for '{created_at}': {e}")
                continue

            if order_date == today:
                today_revenue += total
                today_orders += 1
            if order_date == today - timedelta(days=1):
                yesterday_revenue += total
            if order_date >= first_day_this_month:
                month_revenue += total
                month_orders += 1
            if first_day_last_month <= order_date <= last_day_last_month:
                last_month_revenue += total

        today_growth = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 1) if yesterday_revenue > 0 else (100.0 if today_revenue > 0 else 0)
        month_growth = round(((month_revenue - last_month_revenue) / last_month_revenue) * 100, 1) if last_month_revenue > 0 else (100.0 if month_revenue > 0 else 0)

        print(f"📊 Revenue: Total={total_revenue}, Today={today_revenue}, Month={month_revenue}")

        return jsonify({
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_orders": len(orders),
            "total_items_sold": total_items_sold,
            "today_revenue": today_revenue,
            "today_orders": today_orders,
            "yesterday_revenue": yesterday_revenue,
            "month_revenue": month_revenue,
            "month_orders": month_orders,
            "last_month_revenue": last_month_revenue,
            "today_growth_pct": today_growth,
            "month_growth_pct": month_growth,
        })

    except Exception as exc:
        print(f'❌ Revenue API error: {exc}')
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


def calculate_analytics_from_orders(orders):
    """Helper function to calculate analytics from orders"""
    if not orders:
        return {
            'total_revenue': 0,
            'total_profit': 0,
            'total_orders': 0,
            'total_items_sold': 0,
            'pos_orders_count': 0,
            'web_orders_count': 0,
            'product_sales': {},
            'category_sales': {}
        }
    
    total_revenue = sum(float(order.get('total', 0) or 0) for order in orders)
    total_profit = 0
    total_items_sold = 0
    pos_orders_count = 0
    web_orders_count = 0
    product_sales = {}
    category_sales = {}
    
    for order in orders:
        # Count order sources
        if order.get('source') == 'pos':
            pos_orders_count += 1
        else:
            web_orders_count += 1
        
        # Process items
        for item in order.get('items', []):
            quantity = item.get('quantity', 1)
            total_items_sold += quantity
            
            # Track product sales
            product_id = item.get('product_id') or item.get('id')
            if product_id:
                product_sales[product_id] = product_sales.get(product_id, 0) + quantity
            
            # Track category sales if available
            category = item.get('category')
            if category:
                category_sales[category] = category_sales.get(category, 0) + quantity
            
            # Calculate profit
            price = item.get('price', 0)
            cost_price = item.get('cost_price', 0)
            if cost_price > 0:
                total_profit += (price - cost_price) * quantity
            elif price > 0:
                # If no cost price, assume 30% profit margin
                total_profit += price * quantity * 0.3
    
    return {
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_orders': len(orders),
        'total_items_sold': total_items_sold,
        'pos_orders_count': pos_orders_count,
        'web_orders_count': web_orders_count,
        'product_sales': product_sales,
        'category_sales': category_sales
    }


# ===== DEBUG ENDPOINTS =====

@admin_bp.route('/admin/debug-orders', methods=['GET'])
def debug_orders():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        orders = load_orders()
        total_revenue = sum(float(o.get('total', 0) or 0) for o in orders)
        
        return jsonify({
            'total_orders': len(orders),
            'total_revenue': total_revenue,
            'orders': [
                {
                    'order_id': o.get('order_id'),
                    'total': o.get('total'),
                    'source': o.get('source'),
                    'created_at': o.get('created_at'),
                    'items_count': len(o.get('items', []))
                }
                for o in orders[:20]
            ],
            'raw_orders_count': len(orders),
            'all_totals': [o.get('total') for o in orders[:10]]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@admin_bp.route('/admin/debug-revenue', methods=['GET'])
def debug_revenue():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        orders = load_orders()
        total_revenue = sum(float(o.get('total', 0) or 0) for o in orders)
        
        # Get today's revenue
        today = datetime.utcnow().date()
        today_revenue = 0
        today_orders = 0
        
        for o in orders:
            created_at = o.get('created_at', '')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        if 'T' in created_at:
                            order_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).date()
                        else:
                            order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                    elif isinstance(created_at, datetime):
                        order_date = created_at.date()
                    else:
                        continue
                    
                    if order_date == today:
                        today_revenue += float(o.get('total', 0) or 0)
                        today_orders += 1
                except:
                    pass
        
        return jsonify({
            'total_revenue': total_revenue,
            'today_revenue': today_revenue,
            'total_orders': len(orders),
            'today_orders': today_orders,
            'orders_sample': [
                {
                    'order_id': o.get('order_id'),
                    'total': o.get('total'),
                    'created_at': o.get('created_at')
                }
                for o in orders[:10]
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/admin/test-order', methods=['GET'])
def test_order():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Create a test order
        test_order = {
            'order_id': f'TEST-{uuid.uuid4().hex[:8].upper()}',
            'items': [{
                'name': 'Test Item', 
                'price': 1000, 
                'quantity': 1, 
                'cost_price': 500,
                'product_id': 'test_product'
            }],
            'subtotal': 1000,
            'shipping': 0,
            'total': 1000,
            'status': 'test',
            'source': 'test',
            'created_at': datetime.utcnow().isoformat(),
            'customer': {'name': 'Test Customer'}
        }
        
        # Try to save
        save_result = save_order_to_supabase(test_order)
        
        # Try to load
        orders = load_orders()
        revenue = sum(float(o.get('total', 0) or 0) for o in orders)
        
        return jsonify({
            'save_result': save_result,
            'total_orders': len(orders),
            'total_revenue': revenue,
            'test_order_id': test_order['order_id'],
            'orders_preview': [
                {'id': o.get('order_id'), 'total': o.get('total')} 
                for o in orders[-5:]
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


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
