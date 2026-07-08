import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from calc.basic import add, multiply

def test_add():
    assert add(2, 3) == 5

def test_multiply():
    assert multiply(2, 3) == 6
