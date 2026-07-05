import json
import traceback
import uuid
import os
from datetime import datetime, timedelta

import requests
from flask import session

from config import Config

products_cache = []
orders_cache = []


def has_internet():
    try:
        if not Config.SUPABASE_URL:
            return False
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/",
            headers=Config.SUPABASE_HEADERS,
            timeout=3
        )
        return response.status_code == 200
    except Exception:
        return False


def load_orders():
    """Load orders from Supabase - FORCE REFRESH each time"""
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
                
                # Calculate total revenue for logging
                total_revenue = sum(float(o.get('total', 0) or 0) for o in data)
                print(f"💰 Total revenue from Supabase: {total_revenue}")
                
                orders_cache = data
                return data
        
        print("⚠️ Could not load from Supabase, using cache or empty")
        return orders_cache or []
        
    except Exception as exc:
        print(f'❌ Error loading orders: {exc}')
        traceback.print_exc()
        return orders_cache or []


def load_products():
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
                print(f"✅ Loaded {len(data)} products")
                return data
        
        if products_cache:
            return products_cache
        return get_sample_products()
    except Exception as exc:
        print(f'Error loading products: {exc}')
        return products_cache if products_cache else get_sample_products()


def get_sample_products():
    return [
        {
            'id': 'iphone_15',
            'name': 'iPhone 15 Pro Max',
            'price': 245000,
            'cost_price': 180000,
            'category': 'Phones',
            'description': 'Latest Apple flagship',
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
            'description': 'Professional laptop',
            'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
            'stock': 8,
            'rating': 4.8,
            'reviews': 156,
            'badge': 'New'
        }
    ]


def load_bundles():
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/bundles?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for bundle in data:
                    if 'savings' not in bundle:
                        bundle['savings'] = 0
                return data
        return []
    except Exception as e:
        print(f"Error loading bundles: {e}")
        return []


def save_order_to_supabase(order_data):
    """Save order directly to Supabase"""
    try:
        print(f"💾 Saving order: {order_data.get('order_id')}")
        print(f"💰 Order total: {order_data.get('total')}")
        
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
        
        print(f"📤 Sending to Supabase: {json.dumps(supabase_order)[:200]}...")
        
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=supabase_order,
            timeout=10,
        )
        
        print(f"📤 Supabase response: {response.status_code}")
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Order {order_data.get('order_id')} saved successfully!")
            
            # Clear cache to force reload
            global orders_cache
            orders_cache = None
            
            return {'success': True, 'synced': True, 'queued': False, 'message': 'Order saved successfully.'}
        else:
            print(f"❌ Failed to save: {response.status_code} - {response.text[:200]}")
            return {'success': False, 'synced': False, 'queued': False, 'message': f'Failed: {response.status_code}'}
            
    except Exception as exc:
        print(f'❌ Error saving order: {exc}')
        traceback.print_exc()
        return {'success': False, 'synced': False, 'queued': False, 'message': str(exc)}


def update_product_stock(product_id, new_stock):
    try:
        response = requests.patch(
            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
            headers=Config.SUPABASE_HEADERS,
            json={'stock': new_stock},
            timeout=5,
        )
        return response.status_code in [200, 204]
    except Exception:
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
    """Get sales analytics with proper revenue calculation"""
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
        
        total_revenue = sum(float(o.get('total', 0) or 0) for o in orders)
        total_orders = len(orders)
        
        print(f"💰 Analytics: {total_orders} orders, revenue: {total_revenue}")
        
        return {
            'total_revenue': total_revenue,
            'total_cost': 0,
            'total_profit': total_revenue * 0.3,
            'total_orders': total_orders,
            'total_items_sold': 0,
            'pos_orders_count': 0,
            'web_orders_count': 0,
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
    return True


def sync_pending_data_if_possible():
    return True


def sync_products_from_supabase():
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
