import json
import traceback
import uuid
from datetime import datetime, timedelta

import requests
from flask import session

from config import Config

products_cache = []
orders_cache = []


def get_sample_products():
    return [
        {
            'id': 'iphone_15',
            'name': 'iPhone 15 Pro Max',
            'price': 245000,
            'cost_price': 180000,
            'category': 'Phones',
            'description': 'Latest Apple flagship with A17 Pro chip',
            'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
            'stock': 15,
            'rating': 4.9,
            'reviews': 245,
            'badge': 'Best Seller'
        },
        {
            'id': 'macbook_pro',
            'name': 'MacBook Pro 16"',
            'price': 450000,
            'cost_price': 350000,
            'category': 'Laptops',
            'description': 'Professional laptop with M3 Max chip',
            'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
            'stock': 8,
            'rating': 4.8,
            'reviews': 156,
            'badge': 'New'
        },
        {
            'id': 'airpods_pro',
            'name': 'AirPods Pro 2',
            'price': 35000,
            'cost_price': 22000,
            'category': 'Accessories',
            'description': 'Premium wireless earbuds with ANC',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 25,
            'rating': 4.7,
            'reviews': 389,
            'badge': 'Trending'
        }
    ]


def load_orders():
    """Load orders directly from Supabase - NO LOCAL FILES"""
    global orders_cache
    try:
        print("🔍 Loading orders from Supabase...")
        
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/orders?select=*&order=created_at.desc",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {len(data)} orders in Supabase")
            
            if isinstance(data, list):
                # Clean up data types
                for order in data:
                    if isinstance(order.get('customer'), list):
                        order['customer'] = order['customer'][0] if order['customer'] else {}
                    if isinstance(order.get('items'), str):
                        try:
                            order['items'] = json.loads(order['items'])
                        except Exception:
                            order['items'] = []
                    if not isinstance(order.get('customer'), dict):
                        order['customer'] = {}
                    if not isinstance(order.get('items'), list):
                        order['items'] = []
                
                orders_cache = data
                return data
        
        print(f"⚠️ Supabase returned: {response.status_code}")
        return orders_cache or []
        
    except Exception as exc:
        print(f'❌ Error loading orders: {exc}')
        traceback.print_exc()
        return orders_cache or []


def load_products():
    """Load products directly from Supabase - NO LOCAL FILES"""
    global products_cache
    try:
        print("🔍 Loading products from Supabase...")
        
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/products?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                products_cache = data
                print(f"✅ Loaded {len(data)} products from Supabase")
                return data
        
        print("⚠️ Using cached or sample products")
        return products_cache if products_cache else get_sample_products()
        
    except Exception as exc:
        print(f'❌ Error loading products: {exc}')
        return products_cache if products_cache else get_sample_products()


def load_bundles():
    """Load bundles directly from Supabase - NO LOCAL FILES"""
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/bundles?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                # Ensure each bundle has a savings field
                for bundle in data:
                    if 'savings' not in bundle:
                        bundle['savings'] = 0
                return data
        return []
    except Exception as e:
        print(f"Error loading bundles: {e}")
        return []


def save_order_to_supabase(order_data):
    """Save order directly to Supabase - NO LOCAL FILES"""
    try:
        print(f"💾 Saving order: {order_data.get('order_id')}")
        print(f"💰 Order total: {order_data.get('total')}")
        
        # Prepare data for Supabase
        supabase_order = {
            'order_id': order_data.get('order_id'),
            'items': json.dumps(order_data.get('items', [])),
            'subtotal': float(order_data.get('subtotal', 0)),
            'shipping': float(order_data.get('shipping', 0)),
            'total': float(order_data.get('total', 0)),
            'status': order_data.get('status', 'pending'),
            'source': order_data.get('source', 'web'),
            'created_at': order_data.get('created_at', datetime.utcnow().isoformat()),
            'customer': json.dumps(order_data.get('customer', {}))
        }
        
        print(f"📤 Sending to Supabase...")
        
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=supabase_order,
            timeout=10,
        )
        
        print(f"📤 Supabase response: {response.status_code}")
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Order {order_data.get('order_id')} saved successfully!")
            
            # Clear cache to force reload on next load
            global orders_cache
            orders_cache = None
            
            return {
                'success': True, 
                'synced': True, 
                'queued': False, 
                'message': 'Order saved successfully.'
            }
        else:
            print(f"❌ Failed to save: {response.status_code} - {response.text[:200]}")
            return {
                'success': False, 
                'synced': False, 
                'queued': False, 
                'message': f'Failed to save order: {response.status_code}'
            }
            
    except Exception as exc:
        print(f'❌ Error saving order: {exc}')
        traceback.print_exc()
        return {
            'success': False, 
            'synced': False, 
            'queued': False, 
            'message': f'Database error: {str(exc)}'
        }


def update_product_stock(product_id, new_stock):
    """Update product stock in Supabase"""
    try:
        print(f"📦 Updating stock for product {product_id} to {new_stock}")
        response = requests.patch(
            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
            headers=Config.SUPABASE_HEADERS,
            json={'stock': new_stock},
            timeout=5,
        )
        success = response.status_code in [200, 204]
        if success:
            print(f"✅ Stock updated for {product_id}")
        else:
            print(f"❌ Failed to update stock: {response.status_code}")
        return success
    except Exception as e:
        print(f"❌ Error updating stock: {e}")
        return False


def get_cart():
    try:
        cart = session.get('cart', {})
        if isinstance(cart, list):
            new_cart = {}
            for item_id in cart:
                new_cart[item_id] = new_cart.get(item_id, 0) + 1
            session['cart'] = new_cart
            session.modified = True
            return new_cart
        if not isinstance(cart, dict):
            session['cart'] = {}
            session.modified = True
            return {}
        return cart
    except Exception as exc:
        print(f'Error getting cart: {exc}')
        return {}


def get_sales_analytics():
    """Get sales analytics directly from Supabase"""
    try:
        orders = load_orders()
        
        if not orders:
            return {
                'total_revenue': 0,
                'total_cost': 0,
                'total_profit': 0,
                'total_orders': 0,
                'total_items_sold': 0,
                'pos_orders_count': 0,
                'web_orders_count': 0,
                'total_customers': 0,
                'monthly_data': {},
                'product_sales': {},
                'category_sales': {},
                'customer_data': {}
            }
        
        # Calculate revenue
        total_revenue = sum(float(order.get('total', 0) or 0) for order in orders)
        total_orders = len(orders)
        
        # Calculate POS vs Web orders
        pos_count = sum(1 for o in orders if o.get('source') == 'pos')
        web_count = total_orders - pos_count
        
        print(f"💰 Analytics: {total_orders} orders, revenue: {total_revenue}")
        
        return {
            'total_revenue': total_revenue,
            'total_cost': 0,
            'total_profit': total_revenue * 0.3,
            'total_orders': total_orders,
            'total_items_sold': 0,
            'pos_orders_count': pos_count,
            'web_orders_count': web_count,
            'total_customers': 0,
            'monthly_data': {},
            'product_sales': {},
            'category_sales': {},
            'customer_data': {}
        }
        
    except Exception as exc:
        print(f'Error in analytics: {exc}')
        traceback.print_exc()
        return {
            'total_revenue': 0,
            'total_cost': 0,
            'total_profit': 0,
            'total_orders': 0,
            'total_items_sold': 0,
            'pos_orders_count': 0,
            'web_orders_count': 0,
            'total_customers': 0,
            'monthly_data': {},
            'product_sales': {},
            'customer_data': {},
        }


def sync_queued_orders():
    """No queued orders on Vercel - always sync directly"""
    return True


def sync_pending_data_if_possible():
    """No pending data on Vercel - always sync directly"""
    return True


def sync_products_from_supabase():
    """Sync products from Supabase"""
    return load_products()


def get_category_icon(category):
    icons = {
        'Phones': 'fa-mobile-screen',
        'Laptops': 'fa-laptop',
        'Accessories': 'fa-headphones',
        'Wearables': 'fa-watch',
        'Audio': 'fa-music',
        'Televisions': 'fa-tv',
        'Gaming': 'fa-gamepad',
        'Tablets': 'fa-tablet',
    }
    return icons.get(category, 'fa-box')


def get_all_categories():
    return {
        'Phones': 'fa-mobile-screen',
        'Laptops': 'fa-laptop',
        'Accessories': 'fa-headphones',
        'Wearables': 'fa-watch',
        'Audio': 'fa-music',
        'Televisions': 'fa-tv',
        'Gaming': 'fa-gamepad',
        'Tablets': 'fa-tablet',
    }
