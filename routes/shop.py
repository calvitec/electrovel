import traceback
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from config import Config
from utils.data import (
    get_all_categories,
    get_cart,
    get_category_icon,
    get_sample_products,
    load_bundles,
    load_products,
    save_order_to_supabase,
    update_product_stock,
)

shop_bp = Blueprint('shop', __name__)


@shop_bp.route('/')
def index():
    products_list = load_products()
    bundles_list = load_bundles()

    products_dict = {}
    for product in products_list:
        if product and 'id' in product:
            products_dict[str(product['id'])] = product

    bundles_dict = {}
    for bundle in bundles_list:
        if bundle and 'id' in bundle:
            bundles_dict[str(bundle['id'])] = bundle

    best_sellers = [p for p in products_list if p.get('badge') == 'Best Seller']
    new_arrivals = [p for p in products_list if p.get('badge') == 'New']
    trending = [p for p in products_list if p.get('badge') == 'Trending']

    categories = {}
    for product in products_list:
        cat = product.get('category', 'Other')
        if cat not in categories:
            categories[cat] = {
                'name': cat,
                'icon': get_category_icon(cat),
                'count': 0,
            }
        categories[cat]['count'] += 1

    return render_template(
        'shop.html',
        products=products_dict,
        all_products=products_dict,
        bundles=bundles_dict,
        best_sellers=best_sellers,
        new_arrivals=new_arrivals,
        trending=trending,
        categories=categories,
        CATEGORIES=get_all_categories(),
    )


@shop_bp.route('/category/<category_name>')
def category_page(category_name):
    products = load_products()
    products_dict = {}
    for product in products:
        if product and 'id' in product and product.get('category') == category_name:
            products_dict[str(product['id'])] = product
    return render_template('category.html', products=products_dict, category_name=category_name, CATEGORIES=get_all_categories())


@shop_bp.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = None
    for candidate in products:
        if str(candidate.get('id')) == str(product_id):
            product = candidate
            break

    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('shop.index'))

    related = [p for p in products if p.get('category') == product.get('category') and str(p.get('id')) != product_id][:4]
    related_dict = {}
    for item in related:
        if item and 'id' in item:
            related_dict[str(item['id'])] = item

    return render_template('product.html', product=product, related=related_dict)


@shop_bp.route('/cart')
def cart_page():
    try:
        cart = get_cart()
        cart_items = []
        subtotal = 0
        total_items = 0
        products = load_products()
        bundles = load_bundles()

        for item_id, quantity in cart.items():
            if quantity <= 0:
                continue
            product = next((p for p in products if str(p.get('id')) == str(item_id)), None)
            if product:
                item_total = product.get('price', 0) * quantity
                cart_items.append({
                    'id': item_id,
                    'name': product.get('name', 'Product'),
                    'price': product.get('price', 0),
                    'image': product.get('image', ''),
                    'type': 'product',
                    'quantity': quantity,
                    'item_total': item_total,
                    'stock': product.get('stock', 0),
                    'description': product.get('description', ''),
                    'specs': product.get('specs', []),
                })
                subtotal += item_total
                total_items += quantity
                continue

            for bundle in bundles:
                if str(bundle.get('id')) == str(item_id):
                    item_total = bundle.get('price', 0) * quantity
                    cart_items.append({
                        'id': item_id,
                        'name': bundle.get('name', 'Bundle'),
                        'price': bundle.get('price', 0),
                        'image': bundle.get('image', ''),
                        'type': 'bundle',
                        'quantity': quantity,
                        'item_total': item_total,
                        'products': bundle.get('products', []),
                    })
                    subtotal += item_total
                    total_items += quantity
                    break

        shipping = 0 if subtotal >= 50000 else 800
        total = subtotal + shipping
        return render_template('cart.html', cart_items=cart_items, subtotal=subtotal, shipping=shipping, total=total, total_items=total_items)
    except Exception as exc:
        print(f'Cart error: {exc}')
        flash('Error loading cart', 'danger')
        return redirect(url_for('shop.index'))


@shop_bp.route('/add-to-cart/<item_id>', methods=['POST'])
def add_to_cart(item_id):
    try:
        cart = get_cart()
        products = load_products()
        bundles = load_bundles()

        product = next((p for p in products if str(p.get('id')) == str(item_id)), None)
        if product:
            current_qty = cart.get(item_id, 0)
            if current_qty >= product.get('stock', 0):
                return jsonify({'success': False, 'message': 'Not enough stock available!'})

        bundle_exists = any(str(b.get('id')) == str(item_id) for b in bundles)
        if not product and not bundle_exists:
            return jsonify({'success': False, 'message': 'Item not found'})

        cart[item_id] = cart.get(item_id, 0) + 1
        session['cart'] = cart
        session.modified = True
        total_items = sum(cart.values())
        return jsonify({'success': True, 'message': 'Added to cart!', 'count': total_items, 'quantity': cart[item_id]})
    except Exception as exc:
        print(f'Error adding to cart: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(exc)}'}), 500


@shop_bp.route('/update-cart/<item_id>/<action>', methods=['POST'])
def update_cart_item(item_id, action):
    try:
        cart = get_cart()
        products = load_products()

        if action == 'increase':
            product = next((p for p in products if str(p.get('id')) == str(item_id)), None)
            if product:
                current = cart.get(item_id, 0)
                if current >= product.get('stock', 0):
                    return jsonify({'success': False, 'message': 'Not enough stock available!'})
            cart[item_id] = cart.get(item_id, 0) + 1
        elif action == 'decrease':
            if item_id in cart:
                if cart[item_id] <= 1:
                    del cart[item_id]
                else:
                    cart[item_id] -= 1
            else:
                return jsonify({'success': False, 'message': 'Item not in cart'})
        elif action == 'remove':
            if item_id in cart:
                del cart[item_id]
            else:
                return jsonify({'success': False, 'message': 'Item not in cart'})
        else:
            return jsonify({'success': False, 'message': 'Invalid action'})

        session['cart'] = cart
        session.modified = True

        subtotal = 0
        bundles = load_bundles()
        for iid, qty in cart.items():
            for product in products:
                if str(product.get('id')) == str(iid):
                    subtotal += product.get('price', 0) * qty
                    break
            else:
                for bundle in bundles:
                    if str(bundle.get('id')) == str(iid):
                        subtotal += bundle.get('price', 0) * qty
                        break

        shipping = 0 if subtotal >= 50000 else 800
        total = subtotal + shipping

        item_price = 0
        for product in products:
            if str(product.get('id')) == str(item_id):
                item_price = product.get('price', 0)
                break
        else:
            for bundle in bundles:
                if str(bundle.get('id')) == str(item_id):
                    item_price = bundle.get('price', 0)
                    break

        return jsonify({
            'success': True,
            'quantity': cart.get(item_id, 0),
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
            'total_items': sum(cart.values()),
            'item_total': item_price * cart.get(item_id, 0),
        })
    except Exception as exc:
        print(f'Error updating cart: {exc}')
        return jsonify({'success': False, 'message': str(exc)}), 500


@shop_bp.route('/remove-from-cart/<item_id>', methods=['POST'])
def remove_from_cart(item_id):
    try:
        cart = get_cart()
        if item_id in cart:
            del cart[item_id]
            session['cart'] = cart
            session.modified = True
            return jsonify({'success': True, 'message': 'Removed from cart!', 'count': sum(cart.values())})
        return jsonify({'success': False, 'message': 'Item not in cart'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500


@shop_bp.route('/checkout')
def checkout_page():
    try:
        cart = get_cart()
        if not cart:
            flash('Your cart is empty', 'warning')
            return redirect(url_for('shop.index'))

        cart_items = []
        subtotal = 0
        total_items = 0
        products = load_products()
        bundles = load_bundles()

        for item_id, quantity in cart.items():
            if quantity <= 0:
                continue
            product = next((p for p in products if str(p.get('id')) == str(item_id)), None)
            if product:
                item_total = product.get('price', 0) * quantity
                cart_items.append({
                    'id': item_id,
                    'name': product.get('name', 'Product'),
                    'price': product.get('price', 0),
                    'image': product.get('image', ''),
                    'type': 'product',
                    'quantity': quantity,
                    'item_total': item_total,
                })
                subtotal += item_total
                total_items += quantity
                continue

            for bundle in bundles:
                if str(bundle.get('id')) == str(item_id):
                    item_total = bundle.get('price', 0) * quantity
                    cart_items.append({
                        'id': item_id,
                        'name': bundle.get('name', 'Bundle'),
                        'price': bundle.get('price', 0),
                        'image': bundle.get('image', ''),
                        'type': 'bundle',
                        'quantity': quantity,
                        'item_total': item_total,
                    })
                    subtotal += item_total
                    total_items += quantity
                    break

        shipping = 0 if subtotal >= 50000 else 800
        total = subtotal + shipping
        return render_template('checkout.html', cart_items=cart_items, subtotal=subtotal, shipping=shipping, total=total, total_items=total_items)
    except Exception as exc:
        print(f'Checkout error: {exc}')
        flash('Error loading checkout', 'danger')
        return redirect(url_for('shop.index'))


@shop_bp.route('/place-order', methods=['POST'])
def place_order():
    try:
        cart = get_cart()
        if not cart:
            return jsonify({'success': False, 'message': 'Cart is empty'})

        if request.is_json:
            data = request.get_json()
        else:
            data = {
                'customer_name': request.form.get('customer_name', 'Customer'),
                'customer_email': request.form.get('customer_email', 'customer@example.com'),
                'customer_phone': request.form.get('customer_phone', 'N/A'),
                'customer_address': request.form.get('customer_address', 'N/A'),
            }

        subtotal = 0
        products = load_products()
        bundles = load_bundles()
        order_items = []

        for item_id, quantity in cart.items():
            if quantity <= 0:
                continue
            item_found = False
            for product in products:
                if str(product.get('id')) == str(item_id):
                    current_stock = product.get('stock', 0)
                    if current_stock < quantity:
                        return jsonify({'success': False, 'message': f'Not enough stock for {product.get("name")}. Available: {current_stock}'}), 400
                    item_total = product.get('price', 0) * quantity
                    subtotal += item_total
                    order_items.append({
                        'product_id': item_id,
                        'name': product.get('name'),
                        'price': product.get('price', 0),
                        'quantity': quantity,
                        'total': item_total,
                        'type': 'product',
                    })
                    item_found = True
                    new_stock = max(0, current_stock - quantity)
                    update_product_stock(item_id, new_stock)
                    break

            if not item_found:
                for bundle in bundles:
                    if str(bundle.get('id')) == str(item_id):
                        item_total = bundle.get('price', 0) * quantity
                        subtotal += item_total
                        order_items.append({
                            'product_id': item_id,
                            'name': bundle.get('name'),
                            'price': bundle.get('price', 0),
                            'quantity': quantity,
                            'total': item_total,
                            'type': 'bundle',
                        })
                        break

        if not order_items:
            return jsonify({'success': False, 'message': 'No valid items in cart'}), 400

        shipping = 0 if subtotal >= 50000 else 800
        total = subtotal + shipping
        order_id = f'ELEC-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        customer_name = data.get('customer_name', 'Customer')
        customer_email = data.get('customer_email', 'customer@example.com')
        customer_phone = data.get('customer_phone', 'N/A')
        customer_address = data.get('customer_address', 'N/A')

        order_data = {
            'order_id': order_id,
            'items': order_items,
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
            'status': 'pending',
            'source': 'web',
            'created_at': datetime.utcnow().isoformat(),
            'customer': {
                'name': customer_name,
                'email': customer_email,
                'phone': customer_phone,
                'address': customer_address,
            },
        }

        save_result = save_order_to_supabase(order_data)
        if save_result.get('success'):
            session['cart'] = {}
            session.modified = True
            return jsonify({
                'success': True,
                'order_id': order_id,
                'total': total,
                'message': save_result.get('message', 'Order placed successfully!'),
                'queued': save_result.get('queued', False),
                'synced': save_result.get('synced', False),
            })
        return jsonify({'success': False, 'message': save_result.get('message', 'Failed to save order')}), 500
    except Exception as exc:
        print(f'Error placing order: {exc}')
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(exc)}'}), 500


@shop_bp.route('/order-confirmation/<order_id>')
def order_confirmation(order_id):
    return render_template('confirmation.html', order_id=order_id)


@shop_bp.route('/clear-cart', methods=['POST'])
def clear_cart():
    session['cart'] = {}
    session.modified = True
    return jsonify({'success': True, 'message': 'Cart cleared'})
