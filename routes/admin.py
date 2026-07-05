@admin_bp.route('/admin/direct-test', methods=['GET'])
def direct_test():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    results = {}
    
    # 1. Test Supabase connection directly
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/",
            headers=Config.SUPABASE_HEADERS,
            timeout=5
        )
        results['supabase_connection'] = {
            'status': response.status_code,
            'ok': response.status_code == 200
        }
    except Exception as e:
        results['supabase_connection'] = {'error': str(e)}
    
    # 2. Try to get orders directly from Supabase
    try:
        response = requests.get(
            f"{Config.SUPABASE_URL}/rest/v1/orders?limit=5",
            headers=Config.SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            results['direct_orders'] = {
                'count': len(data),
                'sample': data[:3]
            }
        else:
            results['direct_orders'] = {
                'status': response.status_code,
                'error': response.text[:200]
            }
    except Exception as e:
        results['direct_orders'] = {'error': str(e)}
    
    # 3. Try to save a test order directly
    test_id = f'TEST-{uuid.uuid4().hex[:8]}'
    test_data = {
        'order_id': test_id,
        'items': json.dumps([{'name': 'Test', 'price': 100, 'quantity': 1}]),
        'subtotal': 100,
        'shipping': 0,
        'total': 100,
        'status': 'test',
        'source': 'test',
        'created_at': datetime.utcnow().isoformat(),
        'customer': json.dumps({'name': 'Test'})
    }
    
    try:
        response = requests.post(
            f"{Config.SUPABASE_URL}/rest/v1/orders",
            headers=Config.SUPABASE_HEADERS,
            json=test_data,
            timeout=10
        )
        results['direct_save'] = {
            'status': response.status_code,
            'ok': response.status_code in [200, 201, 204]
        }
        
        # Clean up test
        if response.status_code in [200, 201, 204]:
            requests.delete(
                f"{Config.SUPABASE_URL}/rest/v1/orders?order_id=eq.{test_id}",
                headers=Config.SUPABASE_HEADERS,
                timeout=5
            )
    except Exception as e:
        results['direct_save'] = {'error': str(e)}
    
    # 4. Check load_orders() function
    try:
        orders = load_orders()
        results['load_orders'] = {
            'count': len(orders),
            'sample': orders[:2] if orders else []
        }
    except Exception as e:
        results['load_orders'] = {'error': str(e)}
    
    # 5. Check revenue calculation
    try:
        total = sum(float(o.get('total', 0) or 0) for o in orders)
        results['revenue_calc'] = {
            'total_revenue': total,
            'orders_count': len(orders)
        }
    except Exception as e:
        results['revenue_calc'] = {'error': str(e)}
    
    return jsonify(results)
