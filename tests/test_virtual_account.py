import sys
import os

# Add project root to sys.path so we can import services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from infrastructure.mysql.mysql_adapter import generate_virtual_account

def test_generate_virtual_account():
    # Standard 9-digit case numbers.
    assert generate_virtual_account("115000001") == "99781699115001"
    assert generate_virtual_account("115000010") == "99781699115010"
    assert generate_virtual_account("115000100") == "99781699115100"
    
    # Missing values do not produce an account.
    assert generate_virtual_account(None) == ""
    assert generate_virtual_account("") == ""
    
    # Input must already be the complete canonical case number.
    assert generate_virtual_account("115000001案") == ""
    assert generate_virtual_account("HC115000001") == ""
    assert generate_virtual_account(" 115000001") == ""
    assert generate_virtual_account("115000001 ") == ""
    assert generate_virtual_account("1150000001") == ""
    
    print("All virtual account tests passed successfully!")

if __name__ == "__main__":
    test_generate_virtual_account()
