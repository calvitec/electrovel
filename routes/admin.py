import sys
import os
import json

# Add the project root to Python path so config can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback
import uuid
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for, send_from_directory
from werkzeug.utils import secure_filename

# Now this will work
from config import Config
from utils.data import get_cart, get_sales_analytics, load_bundles, load_orders, load_products, save_order_to_supabase, update_product_stock

# ===== OFFLINE STORAGE =====
from utils.storage import load_json_data, save_json_data

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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Admin access required', 'danger')
            return redirect(url_for('admin.user_login'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    """Decorator to require any logged in user"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            flash('Please login first', 'danger')
            return redirect(url_for('admin.user_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# OFFLINE HELPERS
# ============================================================

def is_supabase_available():
    """Check if Supabase is reachable - using GET instead of HEAD"""
    try:
        # Check if Supabase is configured
        if not Config.SUPABASE_URL or not Config.SUPABASE_HEADERS:
            print("❌ Supabase not configured")
            return False
            
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/products?limit=1",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        # Accept 200, 401, 403 as "reachable" (server is up)
        if response.status_code in [200, 401, 403]:
            print(f"✅ Supabase reachable (status: {response.status_code})")
            return True
        print(f"❌ Supabase check failed: {response.status_code}")
        return False
    except requests.exceptions.Timeout:
        print("❌ Supabase timeout")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Supabase connection error")
        return False
    except Exception as e:
        print(f"❌ Supabase check failed: {e}")
        return False


def save_order_offline(order_data):
    """Save order to offline JSON storage"""
    try:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        
        # Add order to list
        orders.append(order_data)
        json_data['orders'] = orders
        
        # Update stock in JSON
        products = json_data.get('products', [])
        for item in order_data.get('items', []):
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            for p in products:
                if str(p.get('id')) == str(product_id):
                    current_stock = p.get('stock', 0)
                    p['stock'] = max(0, current_stock - quantity)
                    break
        json_data['products'] = products
        
        save_json_data(json_data)
        return True
    except Exception as e:
        print(f"❌ Offline save error: {e}")
        return False


def seed_demo_products():
    """Create demo products if none exist in JSON"""
    demo_products = [
        {'id': 'PROD_1', 'name': 'Wireless Headphones', 'price': 2999, 'stock': 45, 'category': 'Electronics', 'image': '', 'description': 'Premium wireless headphones'},
        {'id': 'PROD_2', 'name': 'USB-C Cable', 'price': 499, 'stock': 120, 'category': 'Accessories', 'image': ''},
        {'id': 'PROD_3', 'name': 'Bluetooth Speaker', 'price': 1499, 'stock': 30, 'category': 'Electronics', 'image': ''},
        {'id': 'PROD_4', 'name': 'Laptop Stand', 'price': 899, 'stock': 25, 'category': 'Furniture', 'image': ''},
        {'id': 'PROD_5', 'name': 'Wireless Mouse', 'price': 699, 'stock': 60, 'category': 'Accessories', 'image': ''},
        {'id': 'PROD_6', 'name': 'Mechanical Keyboard', 'price': 2499, 'stock': 15, 'category': 'Electronics', 'image': ''},
        {'id': 'PROD_7', 'name': 'HDMI Cable', 'price': 299, 'stock': 80, 'category': 'Accessories', 'image': ''},
        {'id': 'PROD_8', 'name': 'USB Hub', 'price': 1299, 'stock': 20, 'category': 'Accessories', 'image': ''},
        {'id': 'PROD_9', 'name': 'Monitor 24"', 'price': 14999, 'stock': 8, 'category': 'Electronics', 'image': ''},
        {'id': 'PROD_10', 'name': 'Desk Lamp', 'price': 599, 'stock': 35, 'category': 'Furniture', 'image': ''},
    ]
    return demo_products


def get_default_users():
    """Default users for offline mode"""
    return [
        {'id': 'admin_1', 'email': 'admin@pricepoint.com', 'password': 'electronics2026', 'name': 'Admin User', 'role': 'admin'},
        {'id': 'manager_1', 'email': 'manager@pricepoint.com', 'password': 'electronics2026', 'name': 'Store Manager', 'role': 'manager'},
        {'id': 'pos_1', 'email': 'pos@pricepoint.com', 'password': 'electronics2026', 'name': 'POS Operator', 'role': 'pos'},
        {'id': 'user_1', 'email': 'user@pricepoint.com', 'password': 'electronics2026', 'name': 'Regular User', 'role': 'user'}
    ]


# ============================================================
# UNIFIED AUTHENTICATION ROUTES (With Offline Support)
# ============================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def user_login():
    """Unified login with database + offline fallback"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash('Please enter both email and password', 'danger')
            return render_template('admin_login.html')
        
        # ============================================================
        # 1. DATABASE AUTHENTICATION (Primary)
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
        # 2. OFFLINE STORAGE AUTHENTICATION (JSON)
        # ============================================================
        data = load_json_data()
        users = data.get('users', [])
        
        # Add default users if none exist
        if not users:
            users = get_default_users()
            data['users'] = users
            save_json_data(data)
        
        for user in users:
            if user.get('email') == email and user.get('password') == password:
                session['user'] = {
                    'id': user.get('id', 'offline_user'),
                    'email': user.get('email'),
                    'name': user.get('name', 'User'),
                    'role': user.get('role', 'user')
                }
                flash('Welcome back, ' + user.get('name', 'User') + '! (Offline Mode)', 'success')
                if user.get('role') == 'admin':
                    return redirect('/admin')
                else:
                    return redirect('/admin/pos')
        
        # ============================================================
        # 3. LEGACY AUTHENTICATION (Fallback)
        # ============================================================
        users_legacy = {
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
        
        if email in users_legacy and users_legacy[email]['password'] == password:
            session['user'] = {
                'email': email,
                'name': users_legacy[email]['name'],
                'role': users_legacy[email]['role'],
                'id': 'legacy_' + email
            }
            flash('Welcome, ' + users_legacy[email]['name'] + '!', 'success')
            return redirect(users_legacy[email]['redirect'])
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
# ADMIN DASHBOARD - ADMIN ONLY
# ============================================================

@admin_bp.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard - with offline support"""
    if not is_admin():
        flash('Admin access required', 'danger')
        return redirect(url_for('admin.user_login'))

    try:
        # Get data with offline fallback
        all_products = []
        all_orders = []
        supabase_available = is_supabase_available()
        
        if supabase_available:
            try:
                all_products = load_products()
                all_orders = load_orders()
                # Cache to JSON
                json_data = load_json_data()
                json_data['products'] = all_products
                json_data['orders'] = all_orders
                save_json_data(json_data)
            except Exception as e:
                print(f"⚠️ Supabase error: {e}")
        
        # Fallback: Load from JSON
        if not all_products:
            json_data = load_json_data()
            all_products = json_data.get('products', [])
            all_orders = json_data.get('orders', [])
            
            # Seed demo products if empty
            if not all_products:
                all_products = seed_demo_products()
                json_data['products'] = all_products
                save_json_data(json_data)
        
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
        
        # Process orders to get customer names and update stats
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
        total_orders = len([o for o in all_orders if o.get('status') != 'cancelled'])
        total_revenue = sum(o.get('total', 0) for o in all_orders if o.get('status') != 'cancelled')
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
        print(f"  📡 Mode: {'Online' if supabase_available else 'Offline'}")
        
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
            'db_mode': 'online' if supabase_available else 'offline',
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
            DB_CONNECTED=supabase_available
        )
        
    except Exception as exc:
        print(f'Admin dashboard error: {exc}')
        traceback.print_exc()
        flash('Error loading admin dashboard (using offline mode)', 'warning')
        
        # Fallback: Load from JSON
        data = load_json_data()
        products = data.get('products', [])
        orders = data.get('orders', [])
        
        return render_template('admin.html', 
            products=products[:10],
            all_products=products,
            total_products=len(products),
            orders=orders[:10],
            recent_orders=orders[:3],
            total_orders=len(orders),
            customers=[], 
            total_customers=0,
            pos_count=0, 
            analytics={}, 
            stats={
                'total_products': len(products),
                'total_bundles': 0,
                'total_cart_items': 0,
                'low_stock': 0,
                'total_orders': len(orders),
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
@login_required
def admin_pos():
    """POS dashboard - with offline support"""
    
    # Try Supabase first, fallback to JSON
    all_products = []
    supabase_available = is_supabase_available()
    
    if supabase_available:
        try:
            all_products = load_products()
            # Cache to JSON
            json_data = load_json_data()
            json_data['products'] = all_products
            save_json_data(json_data)
        except:
            pass
    
    # Fallback: Load from JSON
    if not all_products:
        json_data = load_json_data()
        all_products = json_data.get('products', [])
        
        # Seed demo products if empty
        if not all_products:
            all_products = seed_demo_products()
            json_data['products'] = all_products
            save_json_data(json_data)
    
    # Ensure all products have required fields
    for product in all_products:
        product.setdefault('price', 0)
        product.setdefault('stock', 0)
        product.setdefault('image', '')
        product.setdefault('name', 'Product')
        product.setdefault('id', str(uuid.uuid4()))

    # Get customers (with offline fallback)
    customers = []
    if supabase_available:
        try:
            response = requests.get(
                f"{Config.SUPABASE_URL}/rest/v1/customers",
                headers=Config.SUPABASE_HEADERS,
                timeout=5
            )
            if response.status_code == 200:
                for c in response.json():
                    customers.append({
                        'name': c.get('name', ''),
                        'email': c.get('email', ''),
                        'phone': c.get('phone', ''),
                        'orders': 0,
                        'total_spent': 0
                    })
        except:
            pass
    
    # Fallback: Build customers from JSON orders
    if not customers:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        customer_dict = {}
        for order in orders:
            name = order.get('customer_name')
            if not name or name in ['Walk-in Customer', '']:
                continue
            if name not in customer_dict:
                customer_dict[name] = {
                    'name': name,
                    'email': order.get('customer_email', ''),
                    'phone': order.get('customer_phone', ''),
                    'orders': 0,
                    'total_spent': 0
                }
            customer_dict[name]['orders'] += 1
            customer_dict[name]['total_spent'] += order.get('total', 0)
        customers = list(customer_dict.values())
    
    customers.sort(key=lambda x: x.get('name', ''))
    
    return render_template('pos.html', 
        products=all_products,
        customers=customers,
        DB_CONNECTED=supabase_available,
        offline_mode=not supabase_available
    )


# ============================================================
# POS ORDER ROUTE
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
        
        items = data.get('items', [])
        subtotal = data.get('subtotal', 0)
        shipping = data.get('shipping', 0)
        total = subtotal + shipping

        customer_name = data.get('customer_name', 'Walk-in Customer')
        customer_email = data.get('customer_email', 'walkin@example.com')
        customer_phone = data.get('customer_phone', 'N/A')
        customer_address = data.get('customer_address', 'In-store purchase')

        # ============================================================
        # BUILD ORDER DATA
        # ============================================================
        order_data = {
            'order_id': order_id,
            'items': items,
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
            'user_id': user_id,
            'user_name': user_name,
            'user_role': user_role,
            'staff_name': user_name,
            # ===== OFFLINE TRACKING =====
            'synced': False,
            'synced_at': None
        }

        print(f"👤 ORDER BY: {user_name} (ID: {user_id})")
        print(f"📦 Order ID: {order_id}")

        # ============================================================
        # SAVE TO OFFLINE JSON FIRST (ALWAYS)
        # ============================================================
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        orders.append(order_data)
        json_data['orders'] = orders
        
        # Update stock in JSON
        products = json_data.get('products', [])
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            for p in products:
                if str(p.get('id')) == str(product_id):
                    current_stock = p.get('stock', 0)
                    p['stock'] = max(0, current_stock - quantity)
                    break
        json_data['products'] = products
        save_json_data(json_data)
        print(f"✅ Order saved to JSON: {order_id}")

        # ============================================================
        # TRY SUPABASE (If online)
        # ============================================================
        supabase_success = False
        
        if is_supabase_available():
            try:
                # Load products for cost price
                products_supabase = load_products()
                product_lookup = {str(p.get('id')): p for p in products_supabase}
                
                items_with_cost = []
                for item in items:
                    product_id = str(item.get('product_id'))
                    product = product_lookup.get(product_id)
                    cost_price = product.get('cost_price', 0) if product else 0
                    item_with_cost = item.copy()
                    item_with_cost['cost_price'] = cost_price
                    items_with_cost.append(item_with_cost)
                    
                    # Update stock in Supabase
                    if product:
                        current_stock = product.get('stock', 0)
                        new_stock = max(0, current_stock - quantity)
                        update_product_stock(product_id, new_stock)
                
                order_data['items'] = items_with_cost
                
                # Save to Supabase
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/orders",
                    headers=Config.SUPABASE_HEADERS,
                    json=order_data,
                    timeout=10
                )

                if response.status_code in [200, 201]:
                    supabase_success = True
                    print(f"✅ Order synced to Supabase: {order_id}")
                    
                    # Mark as synced in JSON
                    json_data = load_json_data()
                    for o in json_data.get('orders', []):
                        if o.get('order_id') == order_id:
                            o['synced'] = True
                            o['synced_at'] = datetime.utcnow().isoformat()
                            break
                    save_json_data(json_data)
                    
                    import utils.data
                    utils.data.orders_cache = []
            except Exception as e:
                print(f"⚠️ Supabase sync failed: {e}")

        # ============================================================
        # RETURN RESPONSE
        # ============================================================
        if supabase_success:
            message = f'✅ Order placed! #{order_id} | Total: KSh {total:,.0f} (Synced to cloud)'
        else:
            message = f'✅ Order placed! #{order_id} | Total: KSh {total:,.0f} (Saved offline - will sync when online)'
        
        return jsonify({
            'success': True, 
            'order_id': order_id, 
            'message': message,
            'queued': not supabase_success,
            'synced': supabase_success,
            'offline': not supabase_success,
            'total': total
        })
            
    except Exception as exc:
        print(f'❌ POS Order error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500


# ============================================================
# SYNC QUEUED ORDERS
# ============================================================

@admin_bp.route('/admin/api/sync-queue', methods=['POST'])
@login_required
def api_sync_queue():
    """Sync unsynced orders from JSON to Supabase"""
    try:
        if not is_supabase_available():
            return jsonify({
                'success': True,
                'synced': 0,
                'failed': 0,
                'offline': True,
                'message': 'Supabase offline - orders will sync when online'
            }), 200
        
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        unsynced_orders = [o for o in orders if not o.get('synced', False)]
        
        if not unsynced_orders:
            return jsonify({
                'success': True,
                'synced': 0,
                'failed': 0,
                'message': 'No orders to sync'
            })
        
        print(f"🔄 Syncing {len(unsynced_orders)} offline orders...")
        
        synced = 0
        failed = 0
        
        for order in unsynced_orders:
            try:
                # Ensure all required fields are present
                if 'order_id' not in order:
                    order['order_id'] = f'OFF-{uuid.uuid4().hex[:8].upper()}'
                
                # Ensure created_at is in correct format
                if 'created_at' not in order or not order['created_at']:
                    order['created_at'] = datetime.utcnow().isoformat()
                
                # Handle items format - ensure it's a list of dicts
                items = order.get('items', [])
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except:
                        items = []
                order['items'] = items
                
                # Handle customer format
                customer = order.get('customer', {})
                if isinstance(customer, str):
                    try:
                        customer = json.loads(customer)
                    except:
                        customer = {}
                if not isinstance(customer, dict):
                    customer = {}
                order['customer'] = customer
                
                # Ensure all items have required fields
                for item in order.get('items', []):
                    if 'product_id' not in item:
                        item['product_id'] = str(uuid.uuid4())
                    if 'quantity' not in item:
                        item['quantity'] = 1
                    if 'price' not in item:
                        item['price'] = 0
                    if 'name' not in item:
                        item['name'] = 'Unknown Product'
                
                # Try to save to Supabase
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/orders",
                    headers=Config.SUPABASE_HEADERS,
                    json=order,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    # Mark as synced
                    for o in orders:
                        if o.get('order_id') == order.get('order_id'):
                            o['synced'] = True
                            o['synced_at'] = datetime.utcnow().isoformat()
                            break
                    synced += 1
                    print(f"✅ Synced: {order.get('order_id')}")
                else:
                    failed += 1
                    print(f"❌ Failed to sync: {order.get('order_id')} - {response.status_code} - {response.text[:200]}")
                    
            except Exception as e:
                failed += 1
                print(f"❌ Sync error for {order.get('order_id')}: {e}")
                traceback.print_exc()
        
        # Save updated orders back to JSON
        json_data['orders'] = orders
        save_json_data(json_data)
        
        # Clear cache to force refresh
        import utils.data
        utils.data.orders_cache = []
        
        return jsonify({
            'success': True,
            'synced': synced,
            'failed': failed,
            'message': f"Synced {synced} orders, {failed} failed"
        })
        
    except Exception as e:
        print(f"❌ Sync queue error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# UNSYNCED ORDERS COUNT
# ============================================================

@admin_bp.route('/admin/api/unsynced-count', methods=['GET'])
@login_required
def api_unsynced_count():
    """Get count of unsynced orders"""
    try:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        unsynced = [o for o in orders if not o.get('synced', False)]
        return jsonify({
            'success': True,
            'count': len(unsynced),
            'orders': [o.get('order_id') for o in unsynced[:10]]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PWA ROUTES - PUBLIC
# ============================================================

@admin_bp.route('/offline.html')
def offline_page():
    """Serve offline page - Public route"""
    try:
        return render_template('offline.html')
    except Exception as e:
        print(f"❌ Error serving offline.html: {e}")
        return "Offline page not found", 404


@admin_bp.route('/sw.js')
def service_worker():
    """Serve service worker with correct MIME type - Public route"""
    try:
        return send_from_directory('static', 'sw.js', mimetype='application/javascript')
    except Exception as e:
        print(f"❌ Error serving sw.js: {e}")
        return "Service Worker not found", 404


@admin_bp.route('/manifest.json')
def manifest():
    """Serve manifest.json with correct PWA MIME type - Public route"""
    try:
        return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')
    except Exception as e:
        print(f"❌ Error serving manifest.json: {e}")
        return "Manifest not found", 404


@admin_bp.route('/favicon.ico')
def favicon():
    """Serve favicon - Public route"""
    try:
        return send_from_directory('static/icons', 'favicon.ico', mimetype='image/x-icon')
    except Exception as e:
        print(f"⚠️ Favicon not found: {e}")
        return "", 204


@admin_bp.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files - Public route"""
    try:
        return send_from_directory('static', filename)
    except Exception as e:
        print(f"❌ Error serving static file: {e}")
        return "File not found", 404


# ============================================================
# REMAINING ROUTES - Add all your existing routes below
# ============================================================

# ... (keep all your existing routes: api_analytics, api_revenue, 
#      calculate_analytics_from_orders, api_get_product, 
#      api_get_order, upload_image, admin_products, 
#      admin_delete_product, admin_update_order_status, 
#      api_customers, api_sales_stats, api_process_return)
