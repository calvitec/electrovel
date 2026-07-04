import requests
import json

SUPABASE_URL = "https://hzqrdwerkgfmfaufabjr.supabase.co"
SUPABASE_KEY = "sb_publishable_tnBOmCO7EFfIoXfNjEH_Tg_D7WX-zld"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

print("📥 Downloading data from Supabase...")

# Get products
response = requests.get(f"{SUPABASE_URL}/rest/v1/products?select=*", headers=headers)
if response.status_code == 200:
    products = response.json()
    with open('products.json', 'w') as f:
        json.dump(products, f, indent=2)
    print(f"✅ Saved {len(products)} products to products.json")
else:
    print(f"❌ Failed to get products: {response.status_code}")

# Get orders
response = requests.get(f"{SUPABASE_URL}/rest/v1/orders?select=*", headers=headers)
if response.status_code == 200:
    orders = response.json()
    with open('orders.json', 'w') as f:
        json.dump(orders, f, indent=2)
    print(f"✅ Saved {len(orders)} orders to orders.json")
else:
    print(f"❌ Failed to get orders: {response.status_code}")

print("🎉 Done! Data restored from Supabase.")