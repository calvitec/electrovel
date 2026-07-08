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
# ADMIN DASHBOARD - ADMIN ONLY (FIXED - MERGES DATA FROM BOTH SOURCES)
# ============================================================

@admin_bp.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard - MERGES data from Supabase AND JSON"""
    if not is_admin():
        flash('Admin access required', 'danger')
        return redirect(url_for('admin.user_login'))

    try:
        # ============================================================
        # STEP 1: LOAD DATA FROM BOTH SOURCES
        # ============================================================
        supabase_available = is_supabase_available()
        
        # Load from Supabase
        supabase_products = []
        supabase_orders = []
        
        if supabase_available:
            try:
                supabase_products = load_products() or []
                supabase_orders = load_orders() or []
                print(f"📡 Loaded {len(supabase_products)} products, {len(supabase_orders)} orders from Supabase")
            except Exception as e:
                print(f"⚠️ Supabase load error: {e}")
        
        # Load from JSON
        json_data = load_json_data()
        json_products = json_data.get('products', [])
        json_orders = json_data.get('orders', [])
        print(f"📁 Loaded {len(json_products)} products, {len(json_orders)} orders from JSON")
        
        # ============================================================
        # STEP 2: MERGE DATA - PRIORITIZE JSON FOR ORDERS (Offline orders)
        # ============================================================
        
        # For products: Use Supabase if available, else JSON
        if supabase_products:
            all_products = supabase_products
            # Also cache to JSON
            json_data['products'] = supabase_products
            save_json_data(json_data)
        else:
            all_products = json_products
            # Seed demo products if empty
            if not all_products:
                all_products = seed_demo_products()
                json_data['products'] = all_products
                save_json_data(json_data)
        
        # For orders: MERGE both sources, JSON takes precedence (includes offline orders)
        order_dict = {}
        
        # First add Supabase orders
        for order in supabase_orders:
            order_id = order.get('order_id')
            if order_id:
                order_dict[order_id] = order
        
        # Then add/update with JSON orders (overwrites with local version if exists)
        for order in json_orders:
            order_id = order.get('order_id')
            if order_id:
                # Always use JSON version if it exists (it has the latest data)
                order_dict[order_id] = order
        
        # Convert back to list
        all_orders = list(order_dict.values())
        print(f"🔄 Merged {len(supabase_orders)} Supabase orders + {len(json_orders)} JSON orders = {len(all_orders)} total orders")
        
        # If Supabase was available but we have unsynced orders, trigger auto-sync
        if supabase_available:
            unsynced = [o for o in all_orders if not o.get('synced', False)]
            if unsynced:
                print(f"🔄 Found {len(unsynced)} unsynced orders - they will be synced automatically")
                # Don't sync here to avoid blocking, but the frontend will handle it
        
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
        
        # Count unsynced orders for display
        unsynced_count = len([o for o in all_orders if not o.get('synced', False)])
        
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
        print(f"  📋 Unsynced Orders: {unsynced_count}")
        
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
            'unsynced_orders': unsynced_count,
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
            DB_CONNECTED=supabase_available,
            unsynced_count=unsynced_count
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
                'unsynced_orders': 0,
            }, 
            DB_CONNECTED=False,
            unsynced_count=0
        )


# ============================================================
# POS ROUTE - ACCESSIBLE BY ALL LOGGED-IN USERS (With Offline Support)
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
# POS ORDER ROUTE - ACCESSIBLE BY ALL LOGGED-IN USERS (With Offline Support)
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
        # TRY SUPABASE (If online) - DIRECTLY TO SUPABASE
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
                
                # DIRECTLY SAVE TO SUPABASE (not via Vercel)
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
# USER SALES STATS - Gets stats for the current user (With Offline Support)
# ============================================================

@admin_bp.route('/admin/api/user-stats', methods=['GET'])
@login_required
def api_user_stats():
    """Get sales stats for the current user - works offline!"""
    try:
        user = session.get('user', {})
        user_id = user.get('id', 'unknown')
        user_name = user.get('name', 'Unknown User')
        
        # Load from JSON (always available)
        data = load_json_data()
        orders = data.get('orders', [])
        
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
        
        today = datetime.utcnow().date()
        today_revenue = 0
        today_orders = 0
        total_revenue = 0
        total_orders = len(user_orders)
        
        for order in user_orders:
            if order.get('status') == 'cancelled':
                continue
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
# SYNC QUEUED ORDERS - FIXED: Direct to Supabase
# ============================================================

@admin_bp.route('/admin/api/sync-queue', methods=['POST'])
@login_required
def api_sync_queue():
    """Sync unsynced orders from JSON to Supabase - Direct connection"""
    try:
        # Check Supabase connectivity
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
        
        print(f"🔄 Syncing {len(unsynced_orders)} offline orders to Supabase...")
        
        synced = 0
        failed = 0
        
        for order in unsynced_orders:
            try:
                # Ensure all required fields are present
                if 'order_id' not in order:
                    order['order_id'] = f'OFF-{uuid.uuid4().hex[:8].upper()}'
                
                if 'created_at' not in order or not order['created_at']:
                    order['created_at'] = datetime.utcnow().isoformat()
                
                # Handle items
                items = order.get('items', [])
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except:
                        items = []
                order['items'] = items
                
                # Handle customer
                customer = order.get('customer', {})
                if isinstance(customer, str):
                    try:
                        customer = json.loads(customer)
                    except:
                        customer = {}
                if not isinstance(customer, dict):
                    customer = {}
                order['customer'] = customer
                
                # Ensure items have required fields
                for item in order.get('items', []):
                    if 'product_id' not in item:
                        item['product_id'] = str(uuid.uuid4())
                    if 'quantity' not in item:
                        item['quantity'] = 1
                    if 'price' not in item:
                        item['price'] = 0
                    if 'name' not in item:
                        item['name'] = 'Unknown Product'
                
                # DIRECTLY SYNC TO SUPABASE
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
                    print(f"❌ Failed to sync: {order.get('order_id')} - {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                    
            except Exception as e:
                failed += 1
                print(f"❌ Sync error for {order.get('order_id')}: {e}")
                traceback.print_exc()
        
        # Save updated orders
        json_data['orders'] = orders
        save_json_data(json_data)
        
        # Clear cache
        import utils.data
        utils.data.orders_cache = []
        
        return jsonify({
            'success': True,
            'synced': synced,
            'failed': failed,
            'message': f"Synced {synced} orders to Supabase, {failed} failed"
        })
        
    except Exception as e:
        print(f"❌ Sync queue error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PWA ROUTES - PUBLIC (No login required for browser to detect)
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
# REMAINING ROUTES (With Offline Support)
# ============================================================

@admin_bp.route('/admin/api/analytics')
@login_required
def admin_api_analytics():
    try:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        analytics = calculate_analytics_from_orders(orders)
        return jsonify(analytics)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/admin/api/revenue')
@login_required
def admin_api_revenue():
    try:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        
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
# REST OF ROUTES
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
    
    json_data = load_json_data()
    products = json_data.get('products', [])
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
        json_data = load_json_data()
        products = json_data.get('products', [])
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
        json_data = load_json_data()
        orders = json_data.get('orders', [])
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
        
        # ===== SAVE TO JSON FIRST =====
        json_data = load_json_data()
        products = json_data.get('products', [])
        product_exists = False
        
        for i, p in enumerate(products):
            if p.get('id') == product_id:
                products[i] = data
                product_exists = True
                break
        
        if not product_exists:
            products.append(data)
        
        json_data['products'] = products
        save_json_data(json_data)
        
        # ===== TRY SUPABASE (if online) =====
        supabase_success = False
        if is_supabase_available():
            try:
                if product_exists:
                    response = requests.patch(
                        f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
                        headers=Config.SUPABASE_HEADERS,
                        json=data,
                        timeout=10,
                    )
                else:
                    response = requests.post(
                        f"{Config.SUPABASE_URL}/rest/v1/products",
                        headers=Config.SUPABASE_HEADERS,
                        json=data,
                        timeout=10,
                    )
                
                if response.status_code in [200, 201, 204]:
                    supabase_success = True
                    import utils.data
                    utils.data.products_cache = []
            except Exception as e:
                print(f"⚠️ Supabase sync failed: {e}")
        
        return jsonify({
            'success': True, 
            'message': 'Product saved successfully!' + (' (Synced to cloud)' if supabase_success else ' (Saved offline)'),
            'product': data,
            'offline': not supabase_success
        })
        
    except Exception as exc:
        print(f'Product save error: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(exc)}), 500


@admin_bp.route('/admin/products/<product_id>', methods=['DELETE'])
@admin_required
def admin_delete_product(product_id):
    try:
        # Delete from JSON
        json_data = load_json_data()
        products = json_data.get('products', [])
        json_data['products'] = [p for p in products if p.get('id') != product_id]
        save_json_data(json_data)
        
        # Delete from Supabase (if online)
        if is_supabase_available():
            try:
                response = requests.delete(
                    f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
                    headers=Config.SUPABASE_HEADERS,
                    timeout=5,
                )
                if response.status_code in [200, 204]:
                    import utils.data
                    utils.data.products_cache = []
            except Exception as e:
                print(f"⚠️ Supabase delete failed: {e}")
        
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)})


@admin_bp.route('/admin/orders/<order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    try:
        new_status = request.json.get('status')
        if not new_status:
            return jsonify({'success': False, 'message': 'Status required'}), 400
        
        # Update in JSON
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        for order in orders:
            if order.get('order_id') == order_id:
                order['status'] = new_status
                break
        json_data['orders'] = orders
        save_json_data(json_data)
        
        # Update in Supabase (if online)
        if is_supabase_available():
            try:
                response = requests.patch(
                    f"{Config.SUPABASE_URL}/rest/v1/orders?order_id=eq.{order_id}",
                    headers=Config.SUPABASE_HEADERS,
                    json={'status': new_status},
                    timeout=5,
                )
                if response.status_code in [200, 204]:
                    import utils.data
                    utils.data.orders_cache = []
            except Exception as e:
                print(f"⚠️ Supabase update failed: {e}")
        
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


# ============================================================
# API CUSTOMERS ENDPOINT (With Offline Support)
# ============================================================

@admin_bp.route('/api/customers', methods=['GET'])
@login_required
def api_customers():
    try:
        # Try Supabase first
        if is_supabase_available():
            response = requests.get(
                f"{Config.SUPABASE_URL}/rest/v1/customers",
                headers=Config.SUPABASE_HEADERS,
                timeout=5,
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
        
        # Fallback: Build from JSON orders
        json_data = load_json_data()
        orders = json_data.get('orders', [])
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
# SALES STATS ENDPOINT (With Offline Support)
# ============================================================

@admin_bp.route('/admin/api/sales-stats', methods=['GET'])
@login_required
def api_sales_stats():
    try:
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        products = json_data.get('products', [])
        
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
                
                customer_name = order.get('customer_name', '')
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
        
        total_products = len(products)
        
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
# PROCESS RETURN ENDPOINT (With Offline Support)
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
        
        # ===== SAVE TO JSON FIRST =====
        json_data = load_json_data()
        orders = json_data.get('orders', [])
        orders.append(return_order_data)
        json_data['orders'] = orders
        
        # Restock products in JSON
        products = json_data.get('products', [])
        for item in items_to_return:
            product_id = str(item.get('id', ''))
            quantity = int(item.get('quantity', 1))
            for p in products:
                if str(p.get('id')) == product_id:
                    p['stock'] = p.get('stock', 0) + quantity
                    break
        json_data['products'] = products
        save_json_data(json_data)
        
        # ===== TRY SUPABASE (if online) =====
        supabase_success = False
        if is_supabase_available():
            try:
                # Restock in Supabase
                for item in items_to_return:
                    product_id = str(item.get('id', ''))
                    quantity = int(item.get('quantity', 1))
                    if product_id:
                        products_supabase = load_products()
                        for p in products_supabase:
                            if str(p.get('id')) == product_id:
                                current_stock = int(p.get('stock', 0))
                                new_stock = current_stock + quantity
                                update_product_stock(product_id, new_stock)
                                break
                
                # Save return to Supabase
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/orders",
                    headers=Config.SUPABASE_HEADERS,
                    json=return_order_data,
                    timeout=10,
                )
                
                if response.status_code in [200, 201]:
                    supabase_success = True
                    import utils.data
                    utils.data.orders_cache = []
            except Exception as e:
                print(f"⚠️ Supabase sync failed: {e}")
        
        return jsonify({
            'success': True,
            'order_id': return_order_id,
            'message': f'Return processed! Refund: KSh {refund_total:,.2f}' + (' (Synced to cloud)' if supabase_success else ' (Saved offline)'),
            'refund_total': refund_total,
            'revenue_deducted': refund_total,
            'offline': not supabase_success
        })
            
    except Exception as e:
        print(f'❌ Return error: {e}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
