import pytest
from e_commerce import Product, Order

@pytest.fixture
def sample_order():
    """建立一個含有兩個商品的樣本訂單"""
    order = Order()
    product1 = Product('Laptop', 1000)
    product2 = Product('Mouse', 50)
    order.add_item(product1, 1)
    order.add_item(product2, 2)
    return order

def test_order_total(sample_order):
    """測試訂單總價是否正確"""
    assert sample_order.total() == 1100  # 1000 + (50 * 2)

def test_empty_order():
    """測試空訂單的總價應為0"""
    order = Order()
    assert order.total() == 0

def test_add_item():
    """測試商品能否正確添加到訂單中"""
    order = Order()
    product = Product('Keyboard', 80)
    order.add_item(product, 1)
    assert len(order.items) == 1
    assert order.items[0]['product'].name == 'Keyboard'
    assert order.items[0]['product'].price == 80
    assert order.items[0]['quantity'] == 1