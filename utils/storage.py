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


def has_internet():
    """Check if we can reach Supabase"""
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/",
            headers=Config.SUPABASE_HEADERS,
            timeout=3
        )
        # Any successful response (2xx, 3xx, 4xx) means we can reach the server
        return response.status_code < 500
    except Exception as e:
        print(f"Internet check failed: {e}")
        return False


def get_sample_products():
    return [
        {
            'id': 'iphone_16_pro_max',
            'name': 'iPhone 16 Pro Max',
            'price': 265000,
            'cost_price': 195000,
            'category': 'Phones',
            'description': 'Latest Apple flagship with A18 Pro chip',
            'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
            'stock': 20,
            'rating': 4.9,
            'reviews': 312,
            'badge': 'Best Seller'
        },
        {
            'id': 'iphone_16_pro',
            'name': 'iPhone 16 Pro',
            'price': 235000,
            'cost_price': 175000,
            'category': 'Phones',
            'description': 'Professional iPhone with titanium design',
            'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
            'stock': 18,
            'rating': 4.8,
            'reviews': 256,
            'badge': 'New'
        },
        {
            'id': 'iphone_16',
            'name': 'iPhone 16',
            'price': 195000,
            'cost_price': 145000,
            'category': 'Phones',
            'description': 'Latest iPhone with A18 chip',
            'image': 'https://images.unsplash.com/photo-1592286927505-1def25e4c479?w=500',
            'stock': 25,
            'rating': 4.7,
            'reviews': 189,
            'badge': ''
        },
        {
            'id': 'samsung_s25_ultra',
            'name': 'Samsung Galaxy S25 Ultra',
            'price': 255000,
            'cost_price': 185000,
            'category': 'Phones',
            'description': 'Ultimate Android flagship with 200MP camera',
            'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
            'stock': 15,
            'rating': 4.9,
            'reviews': 278,
            'badge': 'Best Seller'
        },
        {
            'id': 'samsung_s25_plus',
            'name': 'Samsung Galaxy S25 Plus',
            'price': 215000,
            'cost_price': 155000,
            'category': 'Phones',
            'description': 'Premium Android with AI features',
            'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
            'stock': 20,
            'rating': 4.7,
            'reviews': 198,
            'badge': ''
        },
        {
            'id': 'google_pixel_9_pro',
            'name': 'Google Pixel 9 Pro',
            'price': 235000,
            'cost_price': 170000,
            'category': 'Phones',
            'description': 'Pure Android experience with best camera',
            'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
            'stock': 12,
            'rating': 4.8,
            'reviews': 145,
            'badge': 'New'
        },
        {
            'id': 'nothing_phone_3',
            'name': 'Nothing Phone 3',
            'price': 185000,
            'cost_price': 135000,
            'category': 'Phones',
            'description': 'Unique transparent design with Glyph interface',
            'image': 'https://images.unsplash.com/photo-1511707267537-b85faf00021e?w=500',
            'stock': 15,
            'rating': 4.5,
            'reviews': 98,
            'badge': ''
        },
        {
            'id': 'macbook_pro_m4',
            'name': 'MacBook Pro M4 16"',
            'price': 520000,
            'cost_price': 400000,
            'category': 'Laptops',
            'description': 'Professional laptop with M4 Max chip',
            'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
            'stock': 8,
            'rating': 4.9,
            'reviews': 189,
            'badge': 'Best Seller'
        },
        {
            'id': 'macbook_air_m4',
            'name': 'MacBook Air M4 13"',
            'price': 350000,
            'cost_price': 270000,
            'category': 'Laptops',
            'description': 'Ultra-thin laptop with M4 chip',
            'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500',
            'stock': 15,
            'rating': 4.8,
            'reviews': 223,
            'badge': 'New'
        },
        {
            'id': 'dell_xps_16',
            'name': 'Dell XPS 16',
            'price': 280000,
            'cost_price': 210000,
            'category': 'Laptops',
            'description': 'Premium Windows laptop with OLED display',
            'image': 'https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500',
            'stock': 10,
            'rating': 4.6,
            'reviews': 134,
            'badge': ''
        },
        {
            'id': 'lenovo_thinkpad_x1',
            'name': 'Lenovo ThinkPad X1 Carbon',
            'price': 300000,
            'cost_price': 225000,
            'category': 'Laptops',
            'description': 'Business laptop with legendary keyboard',
            'image': 'https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500',
            'stock': 12,
            'rating': 4.7,
            'reviews': 156,
            'badge': ''
        },
        {
            'id': 'hp_spectre_x360_2025',
            'name': 'HP Spectre x360 2025',
            'price': 260000,
            'cost_price': 195000,
            'category': 'Laptops',
            'description': 'Convertible premium laptop',
            'image': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500',
            'stock': 8,
            'rating': 4.5,
            'reviews': 112,
            'badge': ''
        },
        {
            'id': 'asus_zenbook_pro',
            'name': 'Asus Zenbook Pro Duo',
            'price': 320000,
            'cost_price': 240000,
            'category': 'Laptops',
            'description': 'Dual-screen laptop for creators',
            'image': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500',
            'stock': 6,
            'rating': 4.6,
            'reviews': 89,
            'badge': ''
        },
        {
            'id': 'ipad_pro_m4',
            'name': 'iPad Pro M4 13"',
            'price': 220000,
            'cost_price': 165000,
            'category': 'Tablets',
            'description': 'Pro tablet with M4 chip and OLED display',
            'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
            'stock': 15,
            'rating': 4.9,
            'reviews': 245,
            'badge': 'Best Seller'
        },
        {
            'id': 'ipad_air_m3',
            'name': 'iPad Air M3 11"',
            'price': 165000,
            'cost_price': 125000,
            'category': 'Tablets',
            'description': 'Lightweight tablet with M3 chip',
            'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
            'stock': 20,
            'rating': 4.7,
            'reviews': 178,
            'badge': 'New'
        },
        {
            'id': 'samsung_galaxy_tab_s10',
            'name': 'Samsung Galaxy Tab S10 Ultra',
            'price': 210000,
            'cost_price': 155000,
            'category': 'Tablets',
            'description': 'Android flagship tablet',
            'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
            'stock': 12,
            'rating': 4.6,
            'reviews': 145,
            'badge': ''
        },
        {
            'id': 'lenovo_tab_extreme',
            'name': 'Lenovo Tab Extreme',
            'price': 150000,
            'cost_price': 110000,
            'category': 'Tablets',
            'description': 'Large-screen productivity tablet',
            'image': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=500',
            'stock': 10,
            'rating': 4.4,
            'reviews': 78,
            'badge': ''
        },
        {
            'id': 'apple_watch_ultra_3',
            'name': 'Apple Watch Ultra 3',
            'price': 95000,
            'cost_price': 70000,
            'category': 'Wearables',
            'description': 'Rugged smartwatch for extreme sports',
            'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
            'stock': 20,
            'rating': 4.8,
            'reviews': 234,
            'badge': 'Best Seller'
        },
        {
            'id': 'apple_watch_series_10',
            'name': 'Apple Watch Series 10',
            'price': 62000,
            'cost_price': 45000,
            'category': 'Wearables',
            'description': 'Latest Apple Watch with health features',
            'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
            'stock': 30,
            'rating': 4.7,
            'reviews': 312,
            'badge': ''
        },
        {
            'id': 'samsung_galaxy_watch_7',
            'name': 'Samsung Galaxy Watch 7',
            'price': 58000,
            'cost_price': 42000,
            'category': 'Wearables',
            'description': 'Premium Android smartwatch',
            'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
            'stock': 25,
            'rating': 4.6,
            'reviews': 189,
            'badge': ''
        },
        {
            'id': 'garmin_fenix_8',
            'name': 'Garmin Fenix 8',
            'price': 120000,
            'cost_price': 88000,
            'category': 'Wearables',
            'description': 'Professional sports watch with GPS',
            'image': 'https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=500',
            'stock': 10,
            'rating': 4.8,
            'reviews': 98,
            'badge': ''
        },
        {
            'id': 'airpods_max_2',
            'name': 'AirPods Max 2',
            'price': 65000,
            'cost_price': 48000,
            'category': 'Audio',
            'description': 'Premium over-ear headphones',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 20,
            'rating': 4.7,
            'reviews': 234,
            'badge': ''
        },
        {
            'id': 'airpods_pro_3',
            'name': 'AirPods Pro 3',
            'price': 42000,
            'cost_price': 31000,
            'category': 'Audio',
            'description': 'Top-tier wireless earbuds',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 35,
            'rating': 4.8,
            'reviews': 389,
            'badge': 'Best Seller'
        },
        {
            'id': 'airpods_4',
            'name': 'AirPods 4',
            'price': 28000,
            'cost_price': 20000,
            'category': 'Audio',
            'description': 'Most comfortable AirPods',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 40,
            'rating': 4.6,
            'reviews': 267,
            'badge': ''
        },
        {
            'id': 'sony_wh_1000xm6',
            'name': 'Sony WH-1000XM6',
            'price': 58000,
            'cost_price': 42000,
            'category': 'Audio',
            'description': 'Industry-leading noise cancelling',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 15,
            'rating': 4.9,
            'reviews': 178,
            'badge': 'New'
        },
        {
            'id': 'samsung_buds_3_pro',
            'name': 'Samsung Galaxy Buds 3 Pro',
            'price': 35000,
            'cost_price': 25000,
            'category': 'Audio',
            'description': 'Premium earbuds with ANC',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 30,
            'rating': 4.7,
            'reviews': 156,
            'badge': ''
        },
        {
            'id': 'bose_qc_ultra',
            'name': 'Bose QuietComfort Ultra',
            'price': 55000,
            'cost_price': 40000,
            'category': 'Audio',
            'description': 'Comfortable noise-cancelling headphones',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 18,
            'rating': 4.8,
            'reviews': 145,
            'badge': ''
        },
        {
            'id': 'magic_keyboard',
            'name': 'Apple Magic Keyboard',
            'price': 15000,
            'cost_price': 10000,
            'category': 'Accessories',
            'description': 'Premium keyboard for iPad',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 50,
            'rating': 4.5,
            'reviews': 234,
            'badge': ''
        },
        {
            'id': 'apple_pencil_pro',
            'name': 'Apple Pencil Pro',
            'price': 18000,
            'cost_price': 13000,
            'category': 'Accessories',
            'description': 'Precision stylus for iPad Pro',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 45,
            'rating': 4.7,
            'reviews': 189,
            'badge': ''
        },
        {
            'id': 'samsung_pen_s25',
            'name': 'Samsung S Pen Pro',
            'price': 12000,
            'cost_price': 8000,
            'category': 'Accessories',
            'description': 'Stylus for Galaxy devices',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 40,
            'rating': 4.5,
            'reviews': 134,
            'badge': ''
        },
        {
            'id': 'anker_power_bank_30000',
            'name': 'Anker 30000mAh Power Bank',
            'price': 12000,
            'cost_price': 8000,
            'category': 'Accessories',
            'description': 'High-capacity portable charger',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 60,
            'rating': 4.7,
            'reviews': 456,
            'badge': 'Best Seller'
        },
        {
            'id': 'ugreen_100w_charger',
            'name': 'UGREEN 100W USB-C Charger',
            'price': 8500,
            'cost_price': 6000,
            'category': 'Accessories',
            'description': 'GaN fast charger for laptops',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 70,
            'rating': 4.6,
            'reviews': 234,
            'badge': ''
        },
        {
            'id': 'spigen_magsafe_stand',
            'name': 'Spigen MagSafe Stand',
            'price': 7500,
            'cost_price': 5000,
            'category': 'Accessories',
            'description': 'Adjustable wireless charging stand',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 55,
            'rating': 4.4,
            'reviews': 178,
            'badge': ''
        },
        {
            'id': 'belkin_3m_usb_c_cable',
            'name': 'Belkin 3M USB-C Cable',
            'price': 3500,
            'cost_price': 2500,
            'category': 'Accessories',
            'description': 'Durable braided charging cable',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 80,
            'rating': 4.5,
            'reviews': 312,
            'badge': ''
        },
        {
            'id': 'ps5_digital',
            'name': 'PlayStation 5 Digital',
            'price': 85000,
            'cost_price': 65000,
            'category': 'Gaming',
            'description': 'Next-gen gaming console',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 10,
            'rating': 4.9,
            'reviews': 456,
            'badge': 'Best Seller'
        },
        {
            'id': 'xbox_series_x',
            'name': 'Xbox Series X',
            'price': 82000,
            'cost_price': 62000,
            'category': 'Gaming',
            'description': 'Powerful gaming console',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 12,
            'rating': 4.8,
            'reviews': 389,
            'badge': ''
        },
        {
            'id': 'nintendo_switch_2',
            'name': 'Nintendo Switch 2',
            'price': 65000,
            'cost_price': 48000,
            'category': 'Gaming',
            'description': 'Hybrid gaming console',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 15,
            'rating': 4.7,
            'reviews': 234,
            'badge': 'New'
        },
        {
            'id': 'ps5_controller',
            'name': 'PlayStation DualSense',
            'price': 12000,
            'cost_price': 8000,
            'category': 'Gaming',
            'description': 'Wireless controller with haptic feedback',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 40,
            'rating': 4.6,
            'reviews': 567,
            'badge': ''
        },
        {
            'id': 'xbox_elite_2',
            'name': 'Xbox Elite Controller 2',
            'price': 18000,
            'cost_price': 13000,
            'category': 'Gaming',
            'description': 'Pro controller for Xbox',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 25,
            'rating': 4.7,
            'reviews': 189,
            'badge': ''
        },
        {
            'id': 'apple_homepod_2',
            'name': 'Apple HomePod 2',
            'price': 45000,
            'cost_price': 33000,
            'category': 'Smart Home',
            'description': 'Premium smart speaker with spatial audio',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 15,
            'rating': 4.7,
            'reviews': 234,
            'badge': ''
        },
        {
            'id': 'amazon_echo_show_15',
            'name': 'Amazon Echo Show 15',
            'price': 38000,
            'cost_price': 28000,
            'category': 'Smart Home',
            'description': 'Smart display with Fire TV',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 18,
            'rating': 4.5,
            'reviews': 178,
            'badge': ''
        },
        {
            'id': 'google_nest_hub_max',
            'name': 'Google Nest Hub Max',
            'price': 32000,
            'cost_price': 23000,
            'category': 'Smart Home',
            'description': 'Smart display with Google Assistant',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 20,
            'rating': 4.6,
            'reviews': 156,
            'badge': ''
        },
        {
            'id': 'philips_hue_starter',
            'name': 'Philips Hue Starter Kit',
            'price': 25000,
            'cost_price': 18000,
            'category': 'Smart Home',
            'description': 'Smart lighting system',
            'image': 'https://images.unsplash.com/photo-1606841838e0-bf1baf2dc3e9?w=500',
            'stock': 30,
            'rating': 4.7,
            'reviews': 234,
            'badge': ''
        }
    ]


def load_orders():
    """Load orders - try Supabase first, fallback to local"""
    global orders_cache
    
    # Check if we have cached orders and return them
    if orders_cache:
        print(f"📦 Returning {len(orders_cache)} cached orders")
        return orders_cache
    
    try:
        print("🔄 Attempting to load orders from Supabase...")
        
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/orders?select=*&order=created_at.desc",
            headers=Config.SUPABASE_HEADERS,
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Successfully loaded {len(data)} orders from Supabase")
            
            if isinstance(data, list):
                # Process each order to ensure proper format
                processed_orders = []
                for order in data:
                    # Handle customer field - it's already a dict in your DB
                    if isinstance(order.get('customer'), dict):
                        # Already a dict, keep it
                        pass
                    elif isinstance(order.get('customer'), str):
                        try:
                            order['customer'] = json.loads(order['customer'])
                        except:
                            order['customer'] = {}
                    elif isinstance(order.get('customer'), list):
                        order['customer'] = order['customer'][0] if order['customer'] else {}
                    else:
                        order['customer'] = {}
                    
                    # Ensure customer has required fields
                    if not order['customer']:
                        order['customer'] = {
                            'name': order.get('customer_name', 'Customer'),
                            'email': order.get('customer_email', 'N/A'),
                            'phone': order.get('customer_phone', 'N/A'),
                            'address': order.get('customer_address', 'N/A')
                        }
                    
                    # Handle items field
                    if isinstance(order.get('items'), str):
                        try:
                            order['items'] = json.loads(order['items'])
                        except:
                            order['items'] = []
                    elif not isinstance(order.get('items'), list):
                        order['items'] = []
                    
                    # Ensure numeric fields are numbers
                    for field in ['total', 'subtotal', 'shipping']:
                        if field in order:
                            try:
                                order[field] = float(order[field] or 0)
                            except:
                                order[field] = 0
                    
                    # Ensure order_id is a string
                    if 'order_id' in order:
                        order['order_id'] = str(order['order_id'])
                    
                    processed_orders.append(order)
                
                # Cache the processed orders
                orders_cache = processed_orders
                
                # Also update local cache
                try:
                    json_data = load_json_data()
                    json_data['orders'] = processed_orders
                    save_json_data(json_data)
                except Exception as e:
                    print(f"⚠️ Could not update local cache: {e}")
                
                return processed_orders
            else:
                print(f"⚠️ Response is not a list: {type(data)}")
        else:
            print(f"⚠️ Failed to load from Supabase: {response.status_code}")
            print(f"Response: {response.text[:200]}")
        
        # Fallback to local cache
        print("📂 Trying to load from local cache...")
        json_data = load_json_data()
        orders_cache = json_data.get('orders', [])
        print(f"📂 Loaded {len(orders_cache)} orders from local cache")
        return orders_cache
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error loading orders: {e}")
        # Fallback to local cache
        try:
            json_data = load_json_data()
            orders_cache = json_data.get('orders', [])
            print(f"📂 Loaded {len(orders_cache)} orders from local cache (connection error)")
            return orders_cache
        except:
            return []
    except Exception as exc:
        print(f'❌ Error loading orders: {exc}')
        traceback.print_exc()
        
        # Fallback to local cache
        try:
            json_data = load_json_data()
            orders_cache = json_data.get('orders', [])
            print(f"📂 Loaded {len(orders_cache)} orders from local cache (fallback)")
            return orders_cache
        except:
            return []


def load_products():
    """Load products - ALWAYS from Supabase first"""
    global products_cache
    try:
        print("🔄 Attempting to load products from Supabase...")
        
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/products?select=*",
            headers=Config.SUPABASE_HEADERS,
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                products_cache = data
                # Update cache with fresh data
                try:
                    json_data = load_json_data()
                    json_data['products'] = data
                    save_json_data(json_data)
                except Exception as e:
                    print(f"⚠️ Could not update local cache: {e}")
                print(f"✅ Loaded {len(data)} products from Supabase")
                return data
        
        print(f"⚠️ Failed to load products from Supabase: {response.status_code}")
        
        # Only use cache if Supabase fails
        if products_cache:
            print(f"⚠️ Using cached products ({len(products_cache)})")
            return products_cache
        
        json_data = load_json_data()
        products = json_data.get('products', [])
        if products:
            products_cache = products
            print(f"⚠️ Using local cache ({len(products)})")
            return products
        
        print("⚠️ Using sample products")
        return get_sample_products()
    except Exception as exc:
        print(f'Error loading products: {exc}')
        return products_cache if products_cache else get_sample_products()


def load_bundles():
    try:
        if has_internet():
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
    except Exception:
        return []


def sync_products_from_supabase():
    return load_products()


def sync_queued_orders():
    """Sync queued orders when internet is back"""
    try:
        if not has_internet():
            return False
        
        json_data = load_json_data()
        queue = json_data.get('order_queue', [])
        if not queue:
            return True
        
        synced = []
        for order in queue:
            try:
                # Prepare order for Supabase
                supabase_order = {
                    'order_id': order.get('order_id'),
                    'items': order.get('items', []),
                    'subtotal': float(order.get('subtotal', 0)),
                    'shipping': float(order.get('shipping', 0)),
                    'total': float(order.get('total', 0)),
                    'status': order.get('status', 'pending'),
                    'source': order.get('source', 'web'),
                    'created_at': order.get('created_at', datetime.utcnow().isoformat()),
                    'customer': order.get('customer', {}),
                    'customer_name': order.get('customer_name', ''),
                    'customer_email': order.get('customer_email', ''),
                    'customer_phone': order.get('customer_phone', ''),
                    'customer_address': order.get('customer_address', '')
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
                else:
                    print(f"⚠️ Failed to sync order: {order.get('order_id')} - {response.status_code}")
            except Exception as exc:
                print(f'Failed to sync order: {exc}')
        
        if synced:
            json_data['order_queue'] = [o for o in queue if o.get('order_id') not in synced]
            save_json_data(json_data)
            # Clear orders cache to reload fresh data
            global orders_cache
            orders_cache = []
        
        return True
    except Exception as exc:
        print(f'Queue sync error: {exc}')
        return False


def sync_pending_data_if_possible():
    """Sync pending orders if internet is available"""
    if has_internet():
        return sync_queued_orders()
    return False


def save_order_to_supabase(order_data):
    """Save order - try Supabase, fallback to local"""
    try:
        print(f"💾 Saving order: {order_data.get('order_id')}")
        
        # Always save to local first (for offline support)
        json_data = load_json_data()
        json_data.setdefault('orders', [])
        
        # Check if order already exists
        existing_order = None
        for order in json_data['orders']:
            if order.get('order_id') == order_data.get('order_id'):
                existing_order = order
                break
        
        if existing_order:
            # Update existing order
            for key, value in order_data.items():
                existing_order[key] = value
        else:
            # Add new order
            json_data['orders'].append(order_data)
        
        save_json_data(json_data)
        
        # Clear cache to reload fresh data
        global orders_cache
        orders_cache = []
        
        # Try to save to Supabase
        try:
            # Prepare order for Supabase
            supabase_order = {
                'order_id': order_data.get('order_id'),
                'items': order_data.get('items', []),
                'subtotal': float(order_data.get('subtotal', 0)),
                'shipping': float(order_data.get('shipping', 0)),
                'total': float(order_data.get('total', 0)),
                'status': order_data.get('status', 'pending'),
                'source': order_data.get('source', 'web'),
                'created_at': order_data.get('created_at', datetime.utcnow().isoformat()),
                'customer': order_data.get('customer', {}),
                'customer_name': order_data.get('customer_name', ''),
                'customer_email': order_data.get('customer_email', ''),
                'customer_phone': order_data.get('customer_phone', ''),
                'customer_address': order_data.get('customer_address', '')
            }
            
            response = requests.post(
                f"{Config.SUPABASE_URL}/rest/v1/orders",
                headers=Config.SUPABASE_HEADERS,
                json=supabase_order,
                timeout=10,
            )
            
            if response.status_code in [200, 201, 204]:
                print(f"✅ Order saved to Supabase: {order_data.get('order_id')}")
                # Mark as synced
                for order in json_data['orders']:
                    if order.get('order_id') == order_data.get('order_id'):
                        order['synced'] = True
                        order['synced_at'] = datetime.utcnow().isoformat()
                save_json_data(json_data)
                return {'success': True, 'synced': True, 'queued': False, 'message': 'Order saved successfully.'}
            else:
                print(f"⚠️ Supabase save failed: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                # Queue for later sync
                queue = json_data.get('order_queue', [])
                if order_data.get('order_id') not in [q.get('order_id') for q in queue]:
                    queue.append({**order_data, 'queued_at': datetime.utcnow().isoformat()})
                    json_data['order_queue'] = queue
                    save_json_data(json_data)
                return {'success': True, 'synced': False, 'queued': True, 'message': 'Order saved locally. Will sync when internet returns.'}
                
        except Exception as e:
            print(f"❌ Error saving to Supabase: {e}")
            # Queue for later sync
            queue = json_data.get('order_queue', [])
            if order_data.get('order_id') not in [q.get('order_id') for q in queue]:
                queue.append({**order_data, 'queued_at': datetime.utcnow().isoformat()})
                json_data['order_queue'] = queue
                save_json_data(json_data)
            return {'success': True, 'synced': False, 'queued': True, 'message': 'Order saved locally. Will sync when internet returns.'}
        
    except Exception as exc:
        print(f'Error saving order: {exc}')
        traceback.print_exc()
        return {'success': False, 'synced': False, 'queued': False, 'message': str(exc)}


def update_product_stock(product_id, new_stock):
    """Update product stock in Supabase"""
    try:
        print(f"🔄 Updating stock for product {product_id} to {new_stock}")
        
        response = requests.patch(
            f"{Config.SUPABASE_URL}/rest/v1/products?id=eq.{product_id}",
            headers=Config.SUPABASE_HEADERS,
            json={'stock': new_stock},
            timeout=5,
        )
        
        if response.status_code in [200, 204]:
            print(f"✅ Stock updated for {product_id}")
            # Clear cache
            global products_cache
            products_cache = []
            return True
        else:
            print(f"❌ Error updating stock: {response.status_code}")
            return False
    except Exception as exc:
        print(f'Error updating stock: {exc}')
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
            # Skip cancelled orders
            if order.get('status') == 'cancelled':
                continue
                
            # Get customer info
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

            # Get items
            items = order.get('items', [])
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except Exception:
                    items = []
            if not isinstance(items, list):
                items = []

            # Count by source
            source = order.get('source', 'web')
            if source == 'pos':
                pos_orders_count += 1
            else:
                web_orders_count += 1

            # Track customer data
            customer_name = customer.get('name', 'Unknown') if isinstance(customer, dict) else 'Unknown'
            if customer_name != 'Unknown' and customer_name not in customer_data:
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

            # Track monthly data
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

            # Process items
            order_total = float(order.get('total', 0) or 0)
            order_cost = 0.0
            order_items_count = 0

            for item in items:
                product_id = str(item.get('product_id', item.get('id', '')))
                quantity = int(item.get('quantity', 1) or 1)
                price = float(item.get('price', 0) or 0)
                item_total = float(item.get('total', price * quantity) or 0)
                
                # Get cost_price
                cost_price = 0
                
                # First try: cost_price from order item
                if 'cost_price' in item:
                    try:
                        cost_price = float(item.get('cost_price', 0) or 0)
                    except (ValueError, TypeError):
                        cost_price = 0
                
                # Second try: get from product lookup
                if cost_price == 0 and product_id:
                    product = product_lookup.get(product_id, {})
                    if product and 'cost_price' in product:
                        try:
                            cost_price = float(product.get('cost_price', 0) or 0)
                        except (ValueError, TypeError):
                            cost_price = 0
                
                # Final fallback: 70% of price
                if cost_price == 0 and price > 0:
                    cost_price = price * 0.7
                
                # Ensure cost_price is a valid number
                if cost_price is None or cost_price == '' or cost_price != cost_price:
                    cost_price = 0
                
                item_cost = cost_price * quantity
                order_cost += item_cost
                order_items_count += quantity
                total_revenue += item_total
                total_cost += item_cost
                total_profit += (item_total - item_cost)
                total_items_sold += quantity

                # Track product sales
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

                # Track category sales
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

        # Sort by profit
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
        'Smart Home': 'fa-home'
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
        'Smart Home': 'fa-home'
    }
