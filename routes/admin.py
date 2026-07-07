import sys
import os
import json

# Add the project root to Python path so config can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback
import uuid
from datetime import datetime, timedelta

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

# Now this will work
from config import Config
from utils.data import get_cart, get_sales_analytics, load_bundles, load_orders, load_products, save_order_to_supabase, update_product_stock

admin_bp = Blueprint('admin', __name__)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


# ============================================================
# HELPER: Check if user is admin
# ============================================================

def is_admin():
    """Check if current user is admin"""
    user = session.get('user', {})
    return user.get('role') == 'admin' or session.get('admin_logged_in')


def is_logged_in():
    """Check if user is logged in (any role)"""
    return 'user' in session or session.get('admin_logged_in')


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Admin access required', 'danger')
            return redirect(url_for('admin.user_login'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    """Decorator to require any logged in user"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            flash('Please login first', 'danger')
            return redirect(url_for('admin.user_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# UNIFIED AUTHENTICATION ROUTES
# ============================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def user_login():
    """Unified login with database + legacy fallback"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Please enter both email and password', 'danger')
            return render_template('admin_login.html')
        
        # ============================================================
        # DATABASE AUTHENTICATION (Primary)
        # ============================================================
        try:
            try:
                from models.user import User
                user, error = User.authenticate(email, password)
                
                if user:
                    session['user'] = {
                        'id': user.id,
                        'email': user.email,
                        'name': user.full_name,
                        'role': user.role
                    }
                    
                    if user.role == 'admin':
                        flash('Welcome back, ' + user.full_name + '!', 'success')
                        return redirect('/admin')
                    else:
                        flash('Welcome, ' + user.full_name + '!', 'success')
                        return redirect('/admin/pos')
            except ImportError:
                print("⚠️ User model not found, using legacy auth only")
        except Exception as e:
            print(f"DB auth error: {e}")
        
        # ============================================================
        # LEGACY AUTHENTICATION (Fallback)
        # ============================================================
        users = {
            'admin@pricepoint.com': {
                'password': 'electronics2026',
                'name': 'Admin User',
                'role': 'admin',
                'redirect': '/admin'
            },
            'user@pricepoint.com': {
                'password': 'electronics2026',
                'name': 'John Doe',
                'role': 'user',
                'redirect': '/admin/pos'
            },
            'pos@pricepoint.com': {
                'password': 'electronics2026',
                'name': 'POS Operator',
                'role': 'pos',
                'redirect': '/admin/pos'
            },
            'manager@pricepoint.com': {
                'password': 'electronics2026',
                'name': 'Store Manager',
                'role': 'manager',
                'redirect': '/admin/pos'
            }
        }
        
        # Also check username (for old admin login compatibility)
        username = request.form.get('username', '').strip()
        if username == 'admin' and password == 'electronics2026':
            session['admin_logged_in'] = True
            session['user'] = {
                'email': 'admin@pricepoint.com',
                'name': 'Admin User',
                'role': 'admin',
                'id': 'legacy_admin'
            }
            flash('Welcome back, Admin!', 'success')
            return redirect('/admin')
        
        if email in users and users[email]['password'] == password:
            session['user'] = {
                'email': email,
                'name': users[email]['name'],
                'role': users[email]['role'],
                'id': 'legacy_' + email
            }
            flash('Welcome, ' + users[email]['name'] + '!', 'success')
            return redirect(users[email]['redirect'])
        else:
            flash('Invalid email or password', 'danger')
            return render_template('admin_login.html')
    
    return render_template('admin_login.html')


@admin_bp.route('/logout')
def user_logout():
    """Unified logout"""
    session.pop('user', None)
    session.pop('admin_logged_in', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin.user_login'))


# ============================================================
# LEGACY REDIRECTS
# ============================================================

@admin_bp.route('/admin/login')
def admin_login_redirect():
    """Redirect old /admin/login to new /login"""
    return redirect(url_for('admin.user_login'))


@admin_bp.route('/admin/logout')
def admin_logout():
    """Legacy logout - redirect to new logout"""
    session.pop('admin_logged_in', None)
    flash('Logged out', 'success')
    return redirect(url_for('admin.user_login'))


# ============================================================
# ADMIN DASHBOARD - ADMIN ONLY
# ============================================================

@admin_bp.route('/admin')
@admin_required  # ← Only admins can access this!
def admin_dashboard():
    """Admin dashboard - ADMIN ONLY"""
    # Check if user is admin (redundant but safe)
    if not is_admin():
        flash('Admin access required', 'danger')
        return redirect(url_for('admin.user_login'))

    try:
        all_products = load_products()
        all_orders = load_orders()
        bundles = load_bundles()
        cart = get_cart()
        analytics = get_sales_analytics()

        # ===== PAGINATION SETTINGS =====
        per_page = 10
        
        products_page = request.args.get('products_page', 1, type=int)
        orders_page = request.args.get('orders_page', 1, type=int)
        customers_page = request.args.get('customers_page', 1, type=int)

        # ===== CUSTOMER LIST =====
        customer_dict = {}
        pos_count = 0
        web_count = 0
        
        print(f"🔍 Processing {len(all_orders)} orders for customer data...")
        
        # FIRST: Get customers from the customers table
        customers_from_db = []
        try:
            response = requests.get(
                f"{Config.SUPABASE_URL}/rest/v1/customers",
                headers=Config.SUPABASE_HEADERS,
                timeout=10,
            )
            if response.status_code == 200:
                customers_from_db = response.json()
                print(f"✅ Loaded {len(customers_from_db)} customers from database")
                
                for customer in customers_from_db:
                    name = customer.get('name', '')
                    if name and name.strip() and name not in ['Unknown', '']:
                        customer_dict[name] = {
                            'name': name,
                            'email': customer.get('email', 'N/A'),
                            'phone': customer.get('phone', 'N/A'),
                            'orders': 0,
                            'total_spent': 0
                        }
        except Exception as e:
            print(f"⚠️ Error loading customers from database: {e}")
        
        # SECOND: Process orders to get customer names and update stats
        for order in all_orders:
            name = None
            email = None
            phone = None
            
            # Try customer_name field
            if order.get('customer_name'):
                name = order.get('customer_name')
            
            # Try customer object
            if not name:
                customer = order.get('customer', {})
                if isinstance(customer, dict):
                    name = customer.get('name')
                    if not email:
                        email = customer.get('email')
                    if not phone:
                        phone = customer.get('phone')
                elif isinstance(customer, str):
                    try:
                        customer_obj = json.loads(customer)
                        name = customer_obj.get('name')
                        if not email:
                            email = customer_obj.get('email')
                        if not phone:
                            phone = customer_obj.get('phone')
                    except:
                        pass
            
            # Try customer_email as fallback
            if not name:
                email = order.get('customer_email', '')
                if email and '@' in email:
                    name = email.split('@')[0].replace('.', ' ').title()
            
            # Skip generic customers
            if not name or name in ['Walk-in Customer', 'Web Customer', 'Customer', 'Unknown', '']:
                continue
            
            # Get email if not set
            if not email or email == 'N/A':
                email = order.get('customer_email', 'N/A')
                if (not email or email == 'N/A') and isinstance(order.get('customer'), dict):
                    email = order.get('customer', {}).get('email', 'N/A')
            
            # Get phone if not set
            if not phone or phone == 'N/A':
                phone = order.get('customer_phone', 'N/A')
                if (not phone or phone == 'N/A') and isinstance(order.get('customer'), dict):
                    phone = order.get('customer', {}).get('phone', 'N/A')
            
            # Count orders by source
            if order.get('source') == 'pos':
                pos_count += 1
            else:
                web_count += 1
            
            # Add or update customer
            if name not in customer_dict:
                customer_dict[name] = {
                    'name': name,
                    'email': email if email else 'N/A',
                    'phone': phone if phone else 'N/A',
                    'orders': 0,
                    'total_spent': 0
                }
            customer_dict[name]['orders'] += 1
            customer_dict[name]['total_spent'] += order.get('total', 0)
        
        # Convert to list and sort
        customers = list(customer_dict.values())
        customers.sort(key=lambda x: x['orders'], reverse=True)
        
        print(f"✅ Found {len(customers)} unique customers from orders")
        total_customers = len(customers)
        
        # ===== REAL STATS FROM ORDERS =====
        total_orders = len(all_orders)
        total_revenue = sum(order.get('total', 0) for order in all_orders if order.get('status') != 'cancelled')
        pending_orders = len([o for o in all_orders if o.get('status') == 'pending'])
        low_stock_items = len([p for p in all_products if p.get('stock', 0) < 10])
        
        # Calculate today's revenue and orders
        now = datetime.utcnow()
        today = now.date()
        first_day_this_month = today.replace(day=1)
        
        today_revenue = 0
        today_orders = 0
        yesterday_revenue = 0
        month_revenue = 0
        month_orders = 0
        last_month_revenue = 0
        
        # Calculate last month
        if today.month == 1:
            last_month_year = today.year - 1
            last_month_month = 12
        else:
            last_month_year = today.year
            last_month_month = today.month - 1
        
        first_day_last_month = datetime(last_month_year, last_month_month, 1).date()
        if today.month == 1:
            last_day_last_month = datetime(last_month_year, 12, 31).date()
        else:
            last_day_last_month = datetime(today.year, today.month, 1).date() - timedelta(days=1)
        
        for order in all_orders:
            total = order.get('total', 0)
            if isinstance(total, str):
                try:
                    total = float(total.replace(',', ''))
                except:
                    total = 0
            total = float(total or 0)
            
            if order.get('status') == 'cancelled':
                continue
            
            created_at = order.get('created_at', '')
            if not created_at:
                continue
                
            try:
                if isinstance(created_at, datetime):
                    order_date = created_at.date()
                elif isinstance(created_at, str):
                    if 'T' in created_at:
                        clean = created_at.replace('Z', '').replace('+00:00', '')
                        if '.' in clean:
                            order_date = datetime.fromisoformat(clean).date()
                        else:
                            order_date = datetime.strptime(clean[:10], '%Y-%m-%d').date()
                    elif ' ' in created_at:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                    else:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                else:
                    continue
            except Exception as e:
                print(f"Date parse error: {e}")
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
        
        # Calculate growth
        if yesterday_revenue > 0:
            today_growth = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 1)
        else:
            today_growth = 100.0 if today_revenue > 0 else 0
        
        if last_month_revenue > 0:
            month_growth = round(((month_revenue - last_month_revenue) / last_month_revenue) * 100, 1)
        else:
            month_growth = 100.0 if month_revenue > 0 else 0
        
        # Log stats for debugging
        print(f"📊 REAL STATS:")
        print(f"  Total Orders: {total_orders}")
        print(f"  Total Revenue: KSh {total_revenue}")
        print(f"  Pending Orders: {pending_orders}")
        print(f"  Low Stock: {low_stock_items}")
        print(f"  Today Revenue: KSh {today_revenue}")
        print(f"  Today Orders: {today_orders}")
        print(f"  Month Revenue: KSh {month_revenue}")
        print(f"  Today Growth: {today_growth}%")
        print(f"  Month Growth: {month_growth}%")
        
        # ===== CUSTOMERS PAGINATION =====
        total_customer_pages = (total_customers + per_page - 1) // per_page if total_customers > 0 else 1
        if customers_page < 1:
            customers_page = 1
        elif customers_page > total_customer_pages and total_customer_pages > 0:
            customers_page = total_customer_pages
            
        customers_start = (customers_page - 1) * per_page
        customers_end = customers_start + per_page
        paginated_customers = customers[customers_start:customers_end] if customers else []

        # ===== PRODUCTS PAGINATION =====
        total_products = len(all_products)
        total_product_pages = (total_products + per_page - 1) // per_page if total_products > 0 else 1
        if products_page < 1:
            products_page = 1
        elif products_page > total_product_pages and total_product_pages > 0:
            products_page = total_product_pages
            
        products_start = (products_page - 1) * per_page
        products_end = products_start + per_page
        paginated_products = all_products[products_start:products_end] if all_products else []

        # ===== ORDERS PAGINATION =====
        sorted_orders = sorted(all_orders, key=lambda x: x.get('created_at', ''), reverse=True)
        total_order_pages = (total_orders + per_page - 1) // per_page if total_orders > 0 else 1
        if orders_page < 1:
            orders_page = 1
        elif orders_page > total_order_pages and total_order_pages > 0:
            orders_page = total_order_pages
            
        orders_start = (orders_page - 1) * per_page
        orders_end = orders_start + per_page
        paginated_orders = sorted_orders[orders_start:orders_end] if sorted_orders else []
        
        # Recent orders for activity section (always show 3 most recent)
        recent_orders = sorted_orders[:3] if sorted_orders else []

        stats = {
            'total_products': total_products,
            'total_bundles': len(bundles),
            'total_cart_items': sum(cart.values()) if cart else 0,
            'low_stock': low_stock_items,
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'pos_orders': pos_count,
            'web_orders': web_count,
            'total_revenue': total_revenue,
            'total_cost': analytics.get('total_cost', 0),
            'total_profit': analytics.get('total_profit', 0),
            'total_items_sold': analytics.get('total_items_sold', 0),
            'total_customers': total_customers,
            'today_revenue': today_revenue,
            'today_orders': today_orders,
            'yesterday_revenue': yesterday_revenue,
            'month_revenue': month_revenue,
            'month_orders': month_orders,
            'last_month_revenue': last_month_revenue,
            'today_growth_pct': today_growth,
            'month_growth_pct': month_growth,
            'db_mode': 'online',
        }

        print(f"📤 Passing to template: {len(paginated_orders)} orders, {len(paginated_products)} products, {len(paginated_customers)} customers")

        return render_template('admin.html',
            products=paginated_products,
            all_products=all_products,
            total_products=total_products,
            product_page=products_page,
            total_product_pages=total_product_pages,
            orders=paginated_orders,
            recent_orders=recent_orders,
            total_orders=total_orders,
            orders_page=orders_page,
            total_order_pages=total_order_pages,
            customers=paginated_customers,
            total_customers=total_customers,
            customers_page=customers_page,
            total_customer_pages=total_customer_pages,
            per_page=per_page,
            bundles=bundles,
            stats=stats,
            pos_count=pos_count,
            analytics=analytics,
            DB_CONNECTED=True
        )
        
    except Exception as exc:
        print(f'Admin dashboard error: {exc}')
        traceback.print_exc()
        flash('Error loading admin dashboard', 'danger')
        return render_template('admin.html', 
            products=[], 
            bundles=[], 
            orders=[], 
            customers=[], 
            pos_count=0, 
            analytics={}, 
            stats={
                'total_products': 0,
                'total_bundles': 0,
                'total_cart_items': 0,
                'low_stock': 0,
                'total_orders': 0,
                'pending_orders': 0,
                'pos_orders': 0,
                'web_orders': 0,
                'total_revenue': 0,
                'total_cost': 0,
                'total_profit': 0,
                'total_items_sold': 0,
                'total_customers': 0,
                'today_revenue': 0,
                'today_orders': 0,
                'yesterday_revenue': 0,
                'month_revenue': 0,
                'month_orders': 0,
                'last_month_revenue': 0,
                'today_growth_pct': 0,
                'month_growth_pct': 0,
                'db_mode': 'offline',
            }, 
            DB_CONNECTED=False
        )


# ============================================================
# POS ROUTE - ACCESSIBLE BY ALL LOGGED-IN USERS
# ============================================================

@admin_bp.route('/admin/pos')
@login_required  # ← Any logged-in user can access this
def admin_pos():
    """POS dashboard - accessible by all logged-in users"""
    
    all_products = load_products()
    for product in all_products:
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

    # Get customers for POS dropdown
    customers_from_db = []
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/customers",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        if response.status_code == 200:
            customers_from_db = response.json()
            print(f"✅ Loaded {len(customers_from_db)} customers for POS")
    except Exception as e:
        print(f"⚠️ Error loading customers: {e}")
    
    if customers_from_db:
        customers = []
        for c in customers_from_db:
            customers.append({
                'name': c.get('name', ''),
                'email': c.get('email', ''),
                'phone': c.get('phone', ''),
                'orders': 0,
                'total_spent': 0
            })
    else:
        customer_list = {}
        orders = load_orders()
        
        for order in orders:
            name = None
            if order.get('customer_name'):
                name = order.get('customer_name')
            if not name:
                customer = order.get('customer', {})
                if isinstance(customer, dict):
                    name = customer.get('name')
            if not name:
                continue
            
            if name not in customer_list:
                customer_list[name] = {
                    'name': name,
                    'email': order.get('customer_email', ''),
                    'phone': order.get('customer_phone', ''),
                    'orders': 0,
                    'total_spent': 0
                }
            customer_list[name]['orders'] += 1
            customer_list[name]['total_spent'] += order.get('total', 0)
        
        customers = list(customer_list.values())
    
    customers.sort(key=lambda x: x['name'])
    
    return render_template('pos.html', 
        products=all_products,
        customers=customers,
        DB_CONNECTED=True
    )


# ============================================================
# POS ORDER ROUTE - ACCESSIBLE BY ALL LOGGED-IN USERS
# ============================================================

@admin_bp.route('/admin/pos/place-order', methods=['POST'])
@login_required
def admin_pos_place_order():
    try:
        data = request.get_json()
        if not data or not data.get('items'):
            return jsonify({'success': False, 'message': 'No items in order'}), 400

        # ============================================================
        # GET CURRENT USER INFO
        # ============================================================
        user = session.get('user', {})
        user_id = user.get('id', 'unknown')
        user_name = user.get('name', 'Unknown User')
        user_role = user.get('role', 'user')

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
            
            calculated_subtotal += price * quantity
            
            product = product_lookup.get(product_id)
            cost_price = product.get('cost_price', 0) if product else 0
            
            item_with_cost = item.copy()
            item_with_cost['cost_price'] = cost_price
            items_with_cost.append(item_with_cost)
            
            if product:
                current_stock = product.get('stock', 0)
                if current_stock < quantity:
                    return jsonify({
                        'success': False, 
                        'message': f'Not enough stock for {product.get("name")}. Available: {current_stock}'
                    }), 400
                new_stock = max(0, current_stock - quantity)
                update_product_stock(product_id, new_stock)

        subtotal = calculated_subtotal if calculated_subtotal > 0 else data.get('subtotal', 0)
        shipping = data.get('shipping', 0)
        total = subtotal + shipping

        customer_name = data.get('customer_name', '')
        if not customer_name:
            customer_name = data.get('customerName', '')
        if not customer_name:
            customer = data.get('customer', {})
            if isinstance(customer, dict):
                customer_name = customer.get('name', '')
        if not customer_name:
            customer_name = 'Walk-in Customer'
        
        customer_name = customer_name.strip()
        
        customer_email = data.get('customer_email', '') or data.get('customerEmail', '') or 'walkin@example.com'
        customer_phone = data.get('customer_phone', '') or data.get('customerPhone', '') or 'N/A'
        customer_address = data.get('customer_address', '') or data.get('customerAddress', '') or 'In-store purchase'

        # ============================================================
        # ORDER DATA WITH USER TRACKING
        # ============================================================
        order_data = {
            'order_id': order_id,
            'items': items_with_cost,
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
            'status': 'confirmed',
            'source': 'pos',
            'created_at': datetime.utcnow().isoformat(),
            'customer_name': customer_name,
            'customer_email': customer_email,
            'customer_phone': customer_phone,
            'customer_address': customer_address,
            'customer': {
                'name': customer_name,
                'email': customer_email,
                'phone': customer_phone,
                'address': customer_address,
            },
            # ===== USER TRACKING =====
            'user_id': user_id,
            'user_name': user_name,
            'user_role': user_role,
            'staff_name': user_name  # alias for display
        }

        print(f"👤 ORDER BY: {user_name} (ID: {user_id})")
        print(f"🔥 SAVING ORDER WITH CUSTOMER NAME: {customer_name}")
        print(f"📦 Order ID: {order_id}")

        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=order_data,
            timeout=10,
        )

        if response.status_code in [200, 201]:
            print(f"✅ Order saved successfully: {order_id}")
            
            import utils.data
            utils.data.orders_cache = []
            
            all_orders = load_orders()
            
            total_revenue = sum(order.get('total', 0) for order in all_orders)
            
            total_profit = 0
            total_items_sold = 0
            pos_orders_count = 0
            web_orders_count = 0
            
            for order in all_orders:
                if order.get('source') == 'pos':
                    pos_orders_count += 1
                else:
                    web_orders_count += 1
                
                for item in order.get('items', []):
                    quantity = item.get('quantity', 1)
                    total_items_sold += quantity
                    
                    price = item.get('price', 0)
                    cost_price = item.get('cost_price', 0)
                    if cost_price > 0:
                        total_profit += (price - cost_price) * quantity
                    elif price > 0:
                        total_profit += price * quantity * 0.3
            
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
                'queued': False, 
                'synced': True
            })
        else:
            print(f"❌ Supabase error: {response.status_code} - {response.text}")
            return jsonify({
                'success': False, 
                'message': f'Database error: {response.status_code}'
            }), 500
            
    except Exception as exc:
        print(f'POS Order error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500
    
    # ============================================================
# USER SALES STATS - Gets stats for the current user
# ============================================================

@admin_bp.route('/admin/api/user-stats', methods=['GET'])
@login_required
def api_user_stats():
    """Get sales stats for the current user"""
    try:
        user = session.get('user', {})
        user_id = user.get('id', 'unknown')
        user_name = user.get('name', 'Unknown User')
        
        orders = load_orders()
        today = datetime.utcnow().date()
        
        # Filter orders for this user
        user_orders = []
        for order in orders:
            order_user_id = order.get('user_id', '')
            if str(order_user_id) == str(user_id):
                user_orders.append(order)
            # Also check by staff_name/pos_staff
            elif order.get('staff_name') == user_name:
                user_orders.append(order)
            elif order.get('user_name') == user_name:
                user_orders.append(order)
        
        today_revenue = 0
        today_orders = 0
        total_revenue = 0
        total_orders = len(user_orders)
        
        for order in user_orders:
            total_revenue += order.get('total', 0)
            
            created_at = order.get('created_at', '')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        if 'T' in created_at:
                            order_date = datetime.fromisoformat(created_at.replace('Z', '').replace('+00:00', '')).date()
                        else:
                            order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                    elif isinstance(created_at, datetime):
                        order_date = created_at.date()
                    else:
                        continue
                    
                    if order_date == today:
                        today_revenue += order.get('total', 0)
                        today_orders += 1
                except:
                    pass
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'name': user_name
            },
            'today_revenue': today_revenue,
            'today_orders': today_orders,
            'total_revenue': total_revenue,
            'total_orders': total_orders
        })
    except Exception as e:
        print(f"❌ User stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# REMAINING ROUTES (same as before)
# ============================================================

@admin_bp.route('/admin/api/analytics')
@login_required
def admin_api_analytics():
    orders = load_orders()
    analytics = calculate_analytics_from_orders(orders)
    return jsonify(analytics)


@admin_bp.route('/admin/api/revenue')
@login_required
def admin_api_revenue():
    try:
        orders = load_orders()
        
        now = datetime.utcnow()
        today = now.date()
        first_day_this_month = today.replace(day=1)
        
        if today.month == 1:
            last_month_year = today.year - 1
            last_month_month = 12
        else:
            last_month_year = today.year
            last_month_month = today.month - 1
        
        first_day_last_month = datetime(last_month_year, last_month_month, 1).date()
        if today.month == 1:
            last_day_last_month = datetime(last_month_year, 12, 31).date()
        else:
            last_day_last_month = datetime(today.year, today.month, 1).date() - timedelta(days=1)

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
            
            if order.get('status') == 'cancelled':
                continue
            
            created_at = order.get('created_at', '')
            if not created_at:
                continue

            try:
                if isinstance(created_at, datetime):
                    order_date = created_at.date()
                elif isinstance(created_at, str):
                    if 'T' in created_at:
                        clean = created_at.replace('Z', '').replace('+00:00', '')
                        if '.' in clean:
                            order_date = datetime.fromisoformat(clean).date()
                        else:
                            order_date = datetime.strptime(clean[:10], '%Y-%m-%d').date()
                    elif ' ' in created_at:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                    else:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                else:
                    continue
            except Exception as e:
                print(f"Date parse error: {e}")
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

        if yesterday_revenue > 0:
            today_growth = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 1)
        else:
            today_growth = 100.0 if today_revenue > 0 else 0
        
        if last_month_revenue > 0:
            month_growth = round(((month_revenue - last_month_revenue) / last_month_revenue) * 100, 1)
        else:
            month_growth = 100.0 if month_revenue > 0 else 0

        total_revenue = sum(order.get('total', 0) for order in orders if order.get('status') != 'cancelled')

        return jsonify({
            "total_revenue": total_revenue,
            "total_cost": 0,
            "total_profit": 0,
            "total_orders": len(orders),
            "total_items_sold": 0,
            "today_revenue": today_revenue,
            "today_orders": today_orders,
            "yesterday_revenue": yesterday_revenue,
            "month_revenue": month_revenue,
            "month_orders": month_orders,
            "last_month_revenue": last_month_revenue,
            "today_growth_pct": today_growth,
            "month_growth_pct": month_growth
        })

    except Exception as exc:
        print(f'❌ Revenue API error: {exc}')
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# ============================================================
# REST OF ROUTES (same as before)
# ============================================================

def calculate_analytics_from_orders(orders):
    if not orders:
        return {
            'total_revenue': 0,
            'total_cost': 0,
            'total_profit': 0,
            'total_orders': 0,
            'total_items_sold': 0,
            'pos_orders_count': 0,
            'web_orders_count': 0,
            'product_sales': {},
            'category_sales': {},
            'monthly_data': {}
        }
    
    products = load_products()
    product_lookup = {str(p.get('id')): p for p in products if p and p.get('id')}
    
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    total_items_sold = 0
    pos_orders_count = 0
    web_orders_count = 0
    product_sales = {}
    category_sales = {}
    monthly_data = {}
    
    for order in orders:
        if order.get('status') == 'cancelled':
            continue
            
        if order.get('source') == 'pos':
            pos_orders_count += 1
        else:
            web_orders_count += 1
        
        created_at = order.get('created_at', '')
        month_key = 'Unknown'
        if created_at:
            try:
                if isinstance(created_at, str):
                    if 'T' in created_at:
                        clean = created_at.replace('Z', '').replace('+00:00', '')
                        if '.' in clean:
                            dt = datetime.fromisoformat(clean)
                        else:
                            dt = datetime.strptime(clean[:10], '%Y-%m-%d')
                    elif ' ' in created_at:
                        dt = datetime.strptime(created_at[:10], '%Y-%m-%d')
                    else:
                        dt = datetime.strptime(created_at[:10], '%Y-%m-%d')
                elif isinstance(created_at, datetime):
                    dt = created_at
                else:
                    dt = datetime.utcnow()
                month_key = dt.strftime('%b %Y')
            except:
                month_key = 'Unknown'
        
        if month_key not in monthly_data:
            monthly_data[month_key] = {
                'orders': 0,
                'items': 0,
                'revenue': 0,
                'cost': 0,
                'profit': 0,
                'margin': 0
            }
        monthly_data[month_key]['orders'] += 1
        
        order_total = 0
        order_cost = 0
        order_items = 0
        
        for item in order.get('items', []):
            quantity = item.get('quantity', 1)
            price = float(item.get('price', 0) or 0)
            total_items_sold += quantity
            order_items += quantity
            
            item_total = price * quantity
            order_total += item_total
            total_revenue += item_total
            
            cost_price = 0
            
            if 'cost_price' in item:
                try:
                    cost_price = float(item.get('cost_price', 0) or 0)
                except (ValueError, TypeError):
                    cost_price = 0
            
            if cost_price == 0:
                product_id = item.get('product_id', '')
                if product_id:
                    product = product_lookup.get(product_id, {})
                    if product:
                        cost_price = float(product.get('cost_price', 0) or 0)
            
            if cost_price == 0 and price > 0:
                cost_price = price * 0.7
            
            item_cost = cost_price * quantity
            order_cost += item_cost
            total_cost += item_cost
            total_profit += (item_total - item_cost)
            
            product_id = item.get('product_id', '')
            category = 'Uncategorized'
            if product_id:
                product = product_lookup.get(product_id, {})
                if product and product.get('category'):
                    category = product.get('category')
            
            product_name = item.get('name', 'Unknown Product')
            if product_name not in product_sales:
                product_sales[product_name] = {
                    'quantity': 0,
                    'revenue': 0,
                    'cost': 0,
                    'profit': 0,
                    'margin': 0
                }
            product_sales[product_name]['quantity'] += quantity
            product_sales[product_name]['revenue'] += item_total
            product_sales[product_name]['cost'] += item_cost
            product_sales[product_name]['profit'] += (item_total - item_cost)
            
            if category not in category_sales:
                category_sales[category] = {
                    'quantity': 0,
                    'revenue': 0,
                    'cost': 0,
                    'profit': 0,
                    'margin': 0
                }
            category_sales[category]['quantity'] += quantity
            category_sales[category]['revenue'] += item_total
            category_sales[category]['cost'] += item_cost
            category_sales[category]['profit'] += (item_total - item_cost)
        
        monthly_data[month_key]['items'] += order_items
        monthly_data[month_key]['revenue'] += order_total
        monthly_data[month_key]['cost'] += order_cost
        monthly_data[month_key]['profit'] += (order_total - order_cost)
    
    for product in product_sales.values():
        if product['revenue'] > 0:
            product['margin'] = round((product['profit'] / product['revenue']) * 100, 1)
    
    for category in category_sales.values():
        if category['revenue'] > 0:
            category['margin'] = round((category['profit'] / category['revenue']) * 100, 1)
    
    for month in monthly_data.values():
        if month['revenue'] > 0:
            month['margin'] = round((month['profit'] / month['revenue']) * 100, 1)
    
    sorted_products = sorted(
        product_sales.items(),
        key=lambda x: x[1]['profit'],
        reverse=True
    )
    product_sales = dict(sorted_products)
    
    return {
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'total_orders': len(orders),
        'total_items_sold': total_items_sold,
        'pos_orders_count': pos_orders_count,
        'web_orders_count': web_orders_count,
        'product_sales': product_sales,
        'category_sales': category_sales,
        'monthly_data': monthly_data
    }


@admin_bp.route('/api/products/<product_id>', methods=['GET'])
@login_required
def api_get_product(product_id):
    try:
        products = load_products()
        for product in products:
            if str(product.get('id')) == str(product_id):
                return jsonify(product)
        return jsonify({'error': 'Product not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/orders/<order_id>', methods=['GET'])
@login_required
def api_get_order(order_id):
    try:
        orders = load_orders()
        for order in orders:
            if str(order.get('order_id')) == str(order_id):
                customer = order.get('customer', {})
                if isinstance(customer, str):
                    try:
                        customer = json.loads(customer) if customer else {}
                    except:
                        customer = {}
                if isinstance(customer, list):
                    customer = customer[0] if customer else {}
                if not isinstance(customer, dict):
                    customer = {}
                
                items = order.get('items', [])
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except:
                        items = []
                if not isinstance(items, list):
                    items = []
                
                formatted_items = []
                for item in items:
                    if isinstance(item, dict):
                        formatted_items.append({
                            'name': item.get('name', 'Product'),
                            'quantity': item.get('quantity', 1),
                            'price': item.get('price', 0),
                            'total': item.get('total', item.get('price', 0) * item.get('quantity', 1))
                        })
                
                return jsonify({
                    'order_id': order.get('order_id', 'N/A'),
                    'customer': {
                        'name': customer.get('name', order.get('customer_name', 'Customer')),
                        'email': customer.get('email', order.get('customer_email', 'N/A')),
                        'phone': customer.get('phone', order.get('customer_phone', 'N/A')),
                        'address': customer.get('address', order.get('customer_address', 'N/A')),
                    },
                    'items': formatted_items,
                    'subtotal': order.get('subtotal', 0),
                    'shipping': order.get('shipping', 0),
                    'total': order.get('total', 0),
                    'status': order.get('status', 'pending'),
                    'created_at': order.get('created_at', ''),
                    'source': order.get('source', 'web'),
                })
        return jsonify({'error': 'Order not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/admin/upload-image', methods=['POST'])
@login_required
def upload_image():
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
@admin_required
def admin_products():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = {
                'id': request.form.get('id', '').strip(),
                'name': request.form.get('name', '').strip(),
                'price': float(request.form.get('price', 0) or 0),
                'cost_price': float(request.form.get('cost_price', 0) or 0),
                'image': request.form.get('image', '').strip(),
                'category': request.form.get('category', '').strip(),
                'description': request.form.get('description', '').strip(),
                'rating': float(request.form.get('rating', 4.0) or 4.0),
                'reviews': int(request.form.get('reviews', 0) or 0),
                'badge': request.form.get('badge', '').strip(),
                'stock': int(request.form.get('stock', 0) or 0),
                'original_price': float(request.form.get('original_price', 0) or 0) or None,
                'specs': [s.strip() for s in request.form.get('specs', '').split(',') if s.strip()]
            }
        
        product_id = data.get('id', '').strip()
        if not product_id:
            return jsonify({'success': False, 'message': 'Product ID is required'}), 400
        
        existing_products = load_products()
        product_exists = False
        for p in existing_products:
            if p.get('id') == product_id:
                product_exists = True
                break
        
        if product_exists:
            response = requests.patch(
                f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
                headers=Config.SUPABASE_HEADERS,
                json=data,
                timeout=10,
            )
            if response.status_code in [200, 204]:
                import utils.data
                utils.data.products_cache = []
                return jsonify({'success': True, 'message': 'Product updated successfully!', 'product': data})
            else:
                return jsonify({'success': False, 'message': f'Error updating product: {response.status_code}'}), 500
        
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/products",
            headers=Config.SUPABASE_HEADERS,
            json=data,
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            import utils.data
            utils.data.products_cache = []
            return jsonify({'success': True, 'message': 'Product saved successfully!', 'product': data})
        else:
            return jsonify({'success': False, 'message': f'Error saving product: {response.status_code} - {response.text}'}), 500
        
    except Exception as exc:
        print(f'Product save error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500


@admin_bp.route('/admin/products/<product_id>', methods=['DELETE'])
@admin_required
def admin_delete_product(product_id):
    try:
        response = requests.delete(
            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code in [200, 204]:
            import utils.data
            utils.data.products_cache = []
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to delete'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)})


@admin_bp.route('/admin/orders/<order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
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


# ============================================================
# API CUSTOMERS ENDPOINT
# ============================================================

@admin_bp.route('/api/customers', methods=['GET'])
@login_required
def api_customers():
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/customers",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        
        if response.status_code == 200:
            customers_from_db = response.json()
            if customers_from_db:
                result = []
                for c in customers_from_db:
                    result.append({
                        'name': c.get('name', ''),
                        'email': c.get('email', 'N/A'),
                        'phone': c.get('phone', 'N/A'),
                        'orders': 0,
                        'total_spent': 0
                    })
                return jsonify(result)
        
        orders = load_orders()
        customer_dict = {}
        
        for order in orders:
            name = None
            
            if order.get('customer_name'):
                name = order.get('customer_name')
            
            if not name:
                customer = order.get('customer', {})
                if isinstance(customer, dict):
                    name = customer.get('name')
                elif isinstance(customer, str):
                    try:
                        customer_obj = json.loads(customer)
                        name = customer_obj.get('name')
                    except:
                        pass
            
            if not name or name in ['Walk-in Customer', 'Web Customer', 'Customer', '']:
                continue
            
            email = order.get('customer_email', 'N/A')
            phone = order.get('customer_phone', 'N/A')
            
            if name not in customer_dict:
                customer_dict[name] = {
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'orders': 0,
                    'total_spent': 0
                }
            customer_dict[name]['orders'] += 1
            customer_dict[name]['total_spent'] += order.get('total', 0)
        
        return jsonify(list(customer_dict.values()))
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# SALES STATS ENDPOINT
# ============================================================

@admin_bp.route('/admin/api/sales-stats', methods=['GET'])
@login_required
def api_sales_stats():
    try:
        orders = load_orders()
        today = datetime.utcnow().date()
        
        today_revenue = 0
        today_orders = 0
        today_returns = 0
        today_return_amount = 0
        all_customers = set()
        
        for order in orders:
            created_at = order.get('created_at', '')
            if not created_at:
                continue
                
            try:
                order_date = None
                if isinstance(created_at, str):
                    if 'T' in created_at:
                        clean = created_at.replace('Z', '').replace('+00:00', '')
                        if '.' in clean:
                            order_date = datetime.fromisoformat(clean).date()
                        else:
                            order_date = datetime.strptime(clean[:10], '%Y-%m-%d').date()
                    elif ' ' in created_at:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                    else:
                        order_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
                elif isinstance(created_at, datetime):
                    order_date = created_at.date()
                else:
                    continue
                
                customer = order.get('customer', {})
                customer_name = None
                if isinstance(customer, dict):
                    customer_name = customer.get('name', '')
                elif isinstance(customer, str):
                    try:
                        c = json.loads(customer)
                        customer_name = c.get('name', '')
                    except:
                        pass
                
                if customer_name and customer_name not in ['Walk-in Customer', 'Web Customer', '']:
                    all_customers.add(customer_name)
                
                if order_date == today:
                    status = order.get('status', '')
                    total = float(order.get('total', 0))
                    
                    if status == 'returned':
                        today_returns += 1
                        today_return_amount += abs(total)
                        today_revenue += total
                    elif status != 'cancelled':
                        today_revenue += total
                        today_orders += 1
                        
            except Exception as e:
                print(f"Error processing order: {e}")
                continue
        
        total_products = len(load_products())
        
        return jsonify({
            'success': True,
            'today_revenue': today_revenue,
            'today_orders': today_orders,
            'today_returns': today_returns,
            'today_return_amount': today_return_amount,
            'total_customers': len(all_customers),
            'total_products': total_products
        })
    except Exception as e:
        print(f"❌ Sales stats error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PROCESS RETURN ENDPOINT
# ============================================================

@admin_bp.route('/admin/api/process-return', methods=['POST'])
@login_required
def api_process_return():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        items_to_return = data.get('items', [])
        refund_total = data.get('refund_total', 0)
        customer_name = data.get('customer_name', 'Customer')
        reason = data.get('reason', 'Customer return')
        
        if not items_to_return:
            return jsonify({'success': False, 'message': 'No items to return'}), 400
        
        return_items = []
        for item in items_to_return:
            item_price = float(item.get('price', 0))
            item_qty = int(item.get('quantity', 1))
            return_items.append({
                'product_id': str(item.get('id', '')),
                'name': item.get('name', 'Product'),
                'price': item_price,
                'quantity': item_qty,
                'total': item_price * item_qty,
                'type': 'return'
            })
        
        return_order_id = f'RET-{uuid.uuid4().hex[:8].upper()}'
        
        return_order_data = {
            'order_id': return_order_id,
            'items': return_items,
            'subtotal': refund_total,
            'shipping': 0,
            'total': -refund_total,
            'status': 'returned',
            'source': 'pos',
            'created_at': datetime.utcnow().isoformat(),
            'customer': {
                'name': customer_name,
                'email': 'return@example.com',
                'phone': 'N/A',
                'address': 'Return'
            },
            'customer_name': customer_name,
            'customer_email': 'return@example.com',
            'customer_phone': 'N/A',
            'customer_address': 'Return',
            'return_reason': reason,
            'return_amount': refund_total
        }
        
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=return_order_data,
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            for item in items_to_return:
                product_id = str(item.get('id', ''))
                quantity = int(item.get('quantity', 1))
                if product_id:
                    try:
                        products = load_products()
                        for p in products:
                            if str(p.get('id')) == product_id:
                                current_stock = int(p.get('stock', 0))
                                new_stock = current_stock + quantity
                                update_product_stock(product_id, new_stock)
                                break
                    except Exception as e:
                        print(f"⚠️ Error restocking product {product_id}: {e}")
            
            import utils.data
            utils.data.orders_cache = []
            
            return jsonify({
                'success': True,
                'order_id': return_order_id,
                'message': f'Return processed! Refund: KSh {refund_total:,.2f}',
                'refund_total': refund_total,
                'revenue_deducted': refund_total
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to process return: {response.status_code}'
            }), 500
            
    except Exception as e:
        print(f'❌ Return error: {e}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
