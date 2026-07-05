import json
import traceback
import uuid
from datetime import datetime, timedelta

import requests
from flask import session

from config import Config
from utils.storage import load_json_data, save_json_data

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
        },
        {
            'id': 'samsung_s24',
            'name': 'Samsung Galaxy S24 Ultra',
            'price': 225000,
            'cost_price': 115000,
            'category': 'Phones',
            'description': 'Flagship Android phone with advanced camera',
            'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
            'stock': 23,
            'rating': 4.6,
            'reviews': 234
        },
        {
            'id': 'ipad_pro',
            'name': 'iPad Pro 12.9"',
            'price': 185000,
            'cost_price': 140000,
            'category': 'Tablets',
            'description': 'Powerful tablet with M2 chip',
            'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
            'stock': 12,
            'rating': 4.7,
            'reviews': 198,
            'badge': 'New'
        }
    ]


def load_orders():
    """Load orders with merge of queued orders from the right storage"""
    global orders_cache
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/orders?select=*&order=created_at.desc",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
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

                # ===== MERGE QUEUED ORDERS =====
                if Config.IS_VERCEL:
                    # On Vercel - fetch from Supabase order_queue table
                    try:
                        queue_response = requests.get(
                            f"{Config.SUPABASE_URL}/rest/v1/order_queue?select=*",
                            headers=Config.SUPABASE_HEADERS,
                            timeout=5,
                        )
                        if queue_response.status_code == 200:
                            queued_rows = queue_response.json()
                            synced_ids = {o.get('order_id') for o in data}
                            for row in queued_rows:
                                queued_order = row.get('order_data', {})
                                if queued_order.get('order_id') not in synced_ids:
                                    data.append(queued_order)
                    except Exception as e:
                        print(f"Error fetching queued orders from Supabase: {e}")
                else:
                    # Localhost - fetch from local JSON file
                    try:
                        json_data = load_json_data()
                        queue = json_data.get('order_queue', [])
                        synced_ids = {o.get('order_id') for o in data}
                        for queued_order in queue:
                            if queued_order.get('order_id') not in synced_ids:
                                data.append(queued_order)
                    except Exception as e:
                        print(f"Error fetching queued orders from local: {e}")

                orders_cache = data
                return data
        
        print(f"⚠️ Failed to load orders: {response.status_code}")
        return orders_cache or []
        
    except Exception as exc:
        print(f'Error loading orders: {exc}')
        traceback.print_exc()
        return orders_cache or []


def load_products():
    global products_cache
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/products?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                products_cache = data
                return data
        
        if products_cache:
            return products_cache
        return get_sample_products()
    except Exception as exc:
        print(f'Error loading products: {exc}')
        return products_cache if products_cache else get_sample_products()


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
    except Exception:
        return []


def save_order_to_supabase(order_data):
    """Save order - direct to Supabase, with queue fallback per environment"""
    try:
        # Prepare data for Supabase - NO json.dumps() here
        supabase_order = {
            'order_id': order_data.get('order_id'),
            'items': order_data.get('items', []),  # Keep as list
            'subtotal': float(order_data.get('subtotal', 0)),
            'shipping': float(order_data.get('shipping', 0)),
            'total': float(order_data.get('total', 0)),
            'status': order_data.get('status', 'pending'),
            'source': order_data.get('source', 'web'),
            'created_at': order_data.get('created_at', datetime.utcnow().isoformat()),
            'customer': order_data.get('customer', {})  # Keep as dict
        }

        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=supabase_order,
            timeout=10,
        )

        if response.status_code in [200, 201, 204]:
            print(f"✅ Order {order_data.get('order_id')} saved successfully!")
            return {'success': True, 'synced': True, 'queued': False, 'message': 'Order saved successfully.'}

        # ===== INSERT FAILED - queue it =====
        print(f"⚠️ Order insert failed ({response.status_code}), queuing...")
        return _queue_order(order_data)

    except Exception as exc:
        print(f"❌ Error saving order: {exc}")
        return _queue_order(order_data)


def _queue_order(order_data):
    """Queue an order for later sync - uses Supabase on Vercel, local JSON on localhost"""
    
    if Config.IS_VERCEL:
        # ===== ON VERCEL - Use Supabase order_queue table =====
        try:
            queue_data = {
                'order_id': order_data.get('order_id'),
                'order_data': order_data,
                'synced': False,
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = requests.post(
                f"{Config.SUPABASE_URL}/rest/v1/order_queue",
                headers=Config.SUPABASE_HEADERS,
                json=queue_data,
                timeout=10,
            )
            
            if response.status_code in [200, 201, 204]:
                print(f"📦 Order {order_data.get('order_id')} queued in Supabase")
                return {
                    'success': True, 
                    'synced': False, 
                    'queued': True,
                    'message': 'Order queued for sync (stored in database queue).'
                }
            
            print(f"❌ Failed to queue in Supabase: {response.status_code}")
            return {
                'success': False, 
                'synced': False, 
                'queued': False,
                'message': f'Failed to queue order: {response.status_code}'
            }
            
        except Exception as exc:
            print(f"❌ Error queuing in Supabase: {exc}")
            return {
                'success': False, 
                'synced': False, 
                'queued': False,
                'message': f'Could not queue order: {exc}'
            }
    else:
        # ===== LOCALHOST - Use local JSON file =====
        try:
            json_data = load_json_data()
            queue = json_data.get('order_queue', [])
            
            if order_data.get('order_id') not in [q.get('order_id') for q in queue]:
                queue.append({**order_data, 'queued_at': datetime.utcnow().isoformat()})
                json_data['order_queue'] = queue
                save_json_data(json_data)
                print(f"📦 Order {order_data.get('order_id')} queued locally")
            
            return {
                'success': True, 
                'synced': False, 
                'queued': True,
                'message': 'Order saved offline and will sync when internet returns.'
            }
            
        except Exception as exc:
            print(f"❌ Error queuing locally: {exc}")
            return {
                'success': False, 
                'synced': False, 
                'queued': False, 
                'message': str(exc)
            }


def sync_queued_orders():
    """Sync queued orders from the right storage"""
    if Config.IS_VERCEL:
        return _sync_queued_orders_supabase()
    else:
        return _sync_queued_orders_local()


def _sync_queued_orders_supabase():
    """Sync queued orders from Supabase order_queue table"""
    try:
        # Get unsynced queue items
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/order_queue?synced=eq.false",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch queue: {response.status_code}")
            return False
        
        queued_rows = response.json()
        if not queued_rows:
            return True
        
        print(f"📦 Syncing {len(queued_rows)} queued orders from Supabase...")
        
        for row in queued_rows:
            order_data = row.get('order_data', {})
            if not order_data:
                continue
                
            try:
                supabase_order = {
                    'order_id': order_data.get('order_id'),
                    'items': order_data.get('items', []),
                    'subtotal': float(order_data.get('subtotal', 0)),
                    'shipping': float(order_data.get('shipping', 0)),
                    'total': float(order_data.get('total', 0)),
                    'status': order_data.get('status', 'pending'),
                    'source': order_data.get('source', 'web'),
                    'created_at': order_data.get('created_at', datetime.utcnow().isoformat()),
                    'customer': order_data.get('customer', {})
                }
                
                insert_resp = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/orders",
                    headers=Config.SUPABASE_HEADERS,
                    json=supabase_order,
                    timeout=10,
                )
                
                if insert_resp.status_code in [200, 201, 204]:
                    # Mark as synced
                    requests.patch(
                        f"{Config.SUPABASE_URL}/rest/v1/order_queue?id=eq.{row.get('id')}",
                        headers=Config.SUPABASE_HEADERS,
                        json={'synced': True, 'synced_at': datetime.utcnow().isoformat()},
                        timeout=5,
                    )
                    print(f"✅ Synced order: {order_data.get('order_id')}")
                else:
                    print(f"⚠️ Failed to sync order {order_data.get('order_id')}: {insert_resp.status_code}")
                    
            except Exception as e:
                print(f"❌ Error syncing order: {e}")
        
        return True
        
    except Exception as exc:
        print(f'❌ Queue sync error: {exc}')
        traceback.print_exc()
        return False


def _sync_queued_orders_local():
    """Sync queued orders from local JSON file"""
    try:
        json_data = load_json_data()
        queue = json_data.get('order_queue', [])
        if not queue:
            return True

        synced = []
        for order in queue:
            try:
                supabase_order = {
                    'order_id': order.get('order_id'),
                    'items': order.get('items', []),
                    'subtotal': float(order.get('subtotal', 0)),
                    'shipping': float(order.get('shipping', 0)),
                    'total': float(order.get('total', 0)),
                    'status': order.get('status', 'pending'),
                    'source': order.get('source', 'web'),
                    'created_at': order.get('created_at', datetime.utcnow().isoformat()),
                    'customer': order.get('customer', {})
                }
                
                response = requests.post(
                    f"{Config.SUPABASE_URL}/rest/v1/orders",
                    headers=Config.SUPABASE_HEADERS,
                    json=supabase_order,
                    timeout=10,
                )
                
                if response.status_code in [200, 201, 204]:
                    synced.append(order.get('order_id'))
                    print(f"✅ Synced order: {order.get('order_id')}")
                    
            except Exception as exc:
                print(f'Failed to sync order: {exc}')

        if synced:
            json_data['order_queue'] = [o for o in queue if o.get('order_id') not in synced]
            save_json_data(json_data)
            
        return True
        
    except Exception as exc:
        print(f'Local queue sync error: {exc}')
        return False


def sync_products_from_supabase():
    return load_products()


def sync_pending_data_if_possible():
    return sync_queued_orders()


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
    try:
        orders = load_orders()
        total_revenue = sum(float(o.get('total', 0) or 0) for o in orders)
        total_orders = len(orders)
        pos_count = sum(1 for o in orders if o.get('source') == 'pos')
        web_count = total_orders - pos_count
        
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
