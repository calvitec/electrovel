import requests
import json

SUPABASE_URL = "https://hzqrdwerkgfmfaufabjr.supabase.co"
SUPABASE_KEY = "sb_publishable_tnBOmCO7EFfIoXfNjEH_Tg_D7WX-zld"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

response = requests.get(
    f"{SUPABASE_URL}/rest/v1/orders?select=*",
    headers=headers
)

if response.status_code == 200:
    orders = response.json()
    print(f"Total Orders: {len(orders)}")
    
    # Count customers
    customers = set()
    revenue = 0
    for order in orders:
        customer = order.get('customer', {})
        if isinstance(customer, dict):
            name = customer.get('name', 'Unknown')
            customers.add(name)
        revenue += order.get('total', 0)
    
    print(f"Total Customers: {len(customers)}")
    print(f"Total Revenue: KSh {revenue:,.0f}")
else:
    print(f"Error: {response.status_code}")