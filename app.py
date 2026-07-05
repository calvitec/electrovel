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
    """Check if Supabase is reachable"""
    try:
        if not Config.SUPABASE_URL:
            return False
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ Internet check failed: {e}")
        return False


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
        },
        {
            'id': 'hp_spectre',
            'name': 'HP Spectre x360',
            'price': 125000,
            'cost_price': 90000,
            'category': 'Laptops',
            'description': 'Convertible premium laptop',
            'image': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500',
            'stock': 18,
            'rating': 4.5,
            'reviews': 112
        },
        {
            'id': 'watch_9',
            'name': 'Apple Watch Series 9',
            'price': 62000,
            'cost_price': 45000,
            'category': 'Wearables',
            'description': 'Smartwatch with fitness tracking',
            'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
            'stock': 26,
            'rating': 4.8,
            'reviews': 173
        },
        {
            'id': 'usb_c_cable',
            'name': 'USB-C Fast Charging Cable',
            'price': 1200,
            'cost_price': 700,
            'category': 'Accessories',
            'description': 'Fast charging cable',
            'image': 'https://images.unsplash.com/photo-1583394838336-acd977736f90?w=500',
            'stock': 98,
            'rating': 4.4,
            'reviews': 67
        },
        {
            'id': 'dell_xps',
            'name': 'Dell XPS 15',
            'price': 165000,
            'cost_price': 120000,
            'category': 'Laptops',
            'description': 'Thin and powerful productivity laptop',
            'image': 'https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500',
            'stock': 4,
            'rating': 4.6,
            'reviews': 99
        },
        {
            'id': 'power_bank',
            'name': 'Anker 20000mAh Power Bank',
            'price': 8500,
            'cost_price': 5000,
            'category': 'Accessories',
            'description': 'Portable charger for travel',
            'image': 'https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=500',
            'stock': 57,
            'rating': 4.7,
            'reviews': 88
        },
        {
            'id': 'buds_2',
            'name': 'Samsung Galaxy Buds 2',
            'price': 18000,
            'cost_price': 12000,
            'category': 'Audio',
            'description': 'Noise-cancelling earbuds',
            'image': 'https://images.unsplash.com/photo-1606225457115-9b0de873c5e1?w=500',
            'stock': 45,
            'rating': 4.5,
            'reviews': 74
        }
    ]


def load_orders():
    """Load orders directly from Supabase - NO LOCAL FILES on Vercel"""
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
            print(f"📊 Found {len(data)} orders in Supabase")
            
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
                
                orders_cache = data
                return data
        else:
            print(f"⚠️ Supabase returned status: {response.status_code}")
            print(f"⚠️ Response: {response.text[:200]}")
        
        # Fallback to cache if available
        if orders_cache:
            print("⚠️ Using cached orders")
            return orders_cache
        
        print("⚠️ No orders found, returning empty list")
        return []
        
    except Exception as exc:
        print(f'❌ Error loading orders: {exc}')
        traceback.print_exc()
        return orders_cache or []


def load_products():
    """Load products directly from Supabase - NO LOCAL FILES on Vercel"""
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
            elif isinstance(data, list) and len(data) == 0:
                print("⚠️ No products found in Supabase, using sample products")
                return get_sample_products()
        else:
            print(f"⚠️ Supabase returned status: {response.status_code}")
        
        if products_cache:
            return products_cache
            
        return get_sample_products()
        
    except Exception as exc:
        print(f'❌ Error loading products: {exc}')
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
                return data
        return []
    except Exception as e:
        print(f"Error loading bundles: {e}")
        return []


def save_order_to_supabase(order_data):
    """Save order directly to Supabase - NO LOCAL FILES on Vercel"""
    try:
        print(f"💾 Saving order: {order_data.get('order_id')}")
        
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
        
        print(f"📤 Sending to Supabase: {Config.SUPABASE_URL}/rest/v1/orders")
        print(f"📤 Order ID: {order_data.get('order_id')}")
        print(f"📤 Total: {order_data.get('total')}")
        
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=supabase_order,
            timeout=10,
        )
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Order {order_data.get('order_id')} saved to Supabase successfully!")
            return {'success': True, 'synced': True, 'queued': False, 'message': 'Order saved successfully.'}
        else:
            print(f"❌ Supabase error: {response.status_code}")
            print(f"❌ Response: {response.text[:500]}")
            
            # If using publishable key, try to save with service role key from env
            if 'publishable' in Config.SUPABASE_KEY:
                print("⚠️ Using publishable key - trying to save directly...")
                # Try with direct POST with different headers
                try:
                    response2 = requests.post(
                        f"{Config.SUPABASE_URL}/rest/v1/orders",
                        headers={
                            'apikey': Config.SUPABASE_KEY,
                            'Authorization': f'Bearer {Config.SUPABASE_KEY}',
                            'Content-Type': 'application/json',
                            'Prefer': 'return=representation'
                        },
                        json=supabase_order,
                        timeout=10,
                    )
                    if response2.status_code in [200, 201, 204]:
                        print(f"✅ Order saved with direct headers!")
                        return {'success': True, 'synced': True, 'queued': False, 'message': 'Order saved successfully.'}
                except Exception as e2:
                    print(f"❌ Second attempt failed: {e2}")
            
            return {'success': False, 'synced': False, 'queued': False, 'message': f'Failed to save order: {response.status_code}'}
            
    except Exception as exc:
        print(f'❌ Error saving order: {exc}')
        traceback.print_exc()
        return {'success': False, 'synced': False, 'queued': False, 'message': str(exc)}


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
    """Get sales analytics with proper revenue and profit calculation"""
    try:
        orders = load_orders()
        products = load_products()
        
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
        
        product_lookup = {str(p.get('id')): p for p in products if p and p.get('id')}

        total_revenue = 0
        total_cost = 0
        total_profit = 0
        total_orders = len(orders)
        total_items_sold = 0
        pos_orders_count = 0
        web_orders_count = 0
        customer_data = {}
        monthly_data = {}
        product_sales = {}
        category_sales = {}

        for order in orders:
            if order.get('status') == 'cancelled':
                continue
                
            customer = order.get('customer', {})
            if isinstance(customer, str):
                try:
                    customer = json.loads(customer)
                except Exception:
                    customer = {}
            if isinstance(customer, list):
                customer = customer[0] if customer else {}
            if not isinstance(customer, dict):
                customer = {}

            items = order.get('items', [])
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except Exception:
                    items = []
            if not isinstance(items, list):
                items = []

            source = order.get('source', 'web')
            if source == 'pos':
                pos_orders_count += 1
            else:
                web_orders_count += 1

            customer_name = customer.get('name', 'Unknown') if isinstance(customer, dict) else 'Unknown'
            if customer_name not in customer_data and customer_name != 'Unknown':
                customer_data[customer_name] = {
                    'name': customer_name,
                    'email': customer.get('email', ''),
                    'phone': customer.get('phone', ''),
                    'orders': 0,
                    'total_spent': 0,
                }
            if customer_name in customer_data:
                customer_data[customer_name]['orders'] += 1
                customer_data[customer_name]['total_spent'] += float(order.get('total', 0) or 0)

            order_total = float(order.get('total', 0) or 0)
            order_cost = 0.0
            order_items_count = 0

            created_at = order.get('created_at') or order.get('createdAt') or order.get('date') or datetime.utcnow().isoformat()
            try:
                created_dt = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
            except Exception:
                created_dt = datetime.utcnow()
            month_key = created_dt.strftime('%b %Y')
            month_entry = monthly_data.setdefault(month_key, {
                'orders': 0,
                'items': 0,
                'revenue': 0.0,
                'cost': 0.0,
                'profit': 0.0,
            })
            month_entry['orders'] += 1

            for item in items:
                product_id = str(item.get('product_id', item.get('id', '')))
                quantity = int(item.get('quantity', 1) or 1)
                price = float(item.get('price', 0) or 0)
                item_total = float(item.get('total', price * quantity) or 0)
                
                # Get cost price from order item first (stored at time of sale)
                cost_price = float(item.get('cost_price', 0) or 0)
                
                # If no cost in order, try product lookup
                if cost_price == 0 and product_id:
                    product = product_lookup.get(product_id, {})
                    cost_price = float(product.get('cost_price', 0) or 0)
                    
                    if cost_price == 0:
                        cost_price = float(item.get('cost', 0) or 0)
                
                item_cost = cost_price * quantity
                order_cost += item_cost
                order_items_count += quantity
                total_revenue += item_total
                total_cost += item_cost
                total_profit += (item_total - item_cost)
                total_items_sold += quantity

                product_name = product_lookup.get(product_id, {}).get('name') or item.get('name') or f'Product {product_id}'
                sale_entry = product_sales.setdefault(product_name, {
                    'product_id': product_id,
                    'quantity': 0,
                    'revenue': 0.0,
                    'cost': 0.0,
                    'profit': 0.0,
                })
                sale_entry['quantity'] += quantity
                sale_entry['revenue'] += item_total
                sale_entry['cost'] += item_cost
                sale_entry['profit'] += (item_total - item_cost)

                category_name = product_lookup.get(product_id, {}).get('category') or item.get('category') or 'Uncategorized'
                category_entry = category_sales.setdefault(category_name, {
                    'quantity': 0,
                    'revenue': 0.0,
                    'cost': 0.0,
                    'profit': 0.0,
                })
                category_entry['quantity'] += quantity
                category_entry['revenue'] += item_total
                category_entry['cost'] += item_cost
                category_entry['profit'] += (item_total - item_cost)

            month_entry['items'] += order_items_count
            month_entry['revenue'] += order_total
            month_entry['cost'] += order_cost
            month_entry['profit'] += (order_total - order_cost)

        sorted_product_sales = dict(sorted(product_sales.items(), key=lambda item: item[1].get('profit', 0), reverse=True))
        sorted_category_sales = dict(sorted(category_sales.items(), key=lambda item: item[1].get('revenue', 0), reverse=True))

        return {
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_orders': total_orders,
            'total_items_sold': total_items_sold,
            'pos_orders_count': pos_orders_count,
            'web_orders_count': web_orders_count,
            'total_customers': len(customer_data),
            'monthly_data': monthly_data,
            'product_sales': sorted_product_sales,
            'all_product_sales': sorted_product_sales,
            'category_sales': sorted_category_sales,
            'customer_data': customer_data,
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


# Keep these for compatibility but they do nothing on Vercel
def load_json_data():
    return {}


def save_json_data(data):
    pass
