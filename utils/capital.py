"""
Capital.com API utilities
"""
import os
import requests
from typing import Dict, Optional, Any


class CapitalAPI:
    """
    Capital.com API client for trading operations
    """
    
    def __init__(self, api_key: str = None, password: str = None, identifier: str = None):
        """Initialize Capital.com API client"""
        self.api_key = api_key or os.getenv('CAPITAL_API_KEY', '')
        self.password = password or os.getenv('CAPITAL_API_PASSWORD', '')
        self.identifier = identifier or os.getenv('CAPITAL_API_IDENTIFIER', '')
        
        self.base_url = "https://api-capital.backend-capital.com/api/v1"
        self.session_token = None
        self.cst = None
    
    def login(self) -> bool:
        """
        Authenticate with Capital.com API
        
        Returns:
            True if login successful
        """
        url = f"{self.base_url}/session"
        headers = {
            'X-CAP-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }
        payload = {
            'identifier': self.identifier,
            'password': self.password
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.cst = response.headers.get('CST')
                self.session_token = response.headers.get('X-SECURITY-TOKEN')
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self.session_token:
            self.login()
        
        url = f"{self.base_url}/accounts"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"❌ Error fetching account info: {e}")
            return None
    
    def create_position(
        self,
        epic: str,
        direction: str,
        size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create a new position
        
        Args:
            epic: Market identifier
            direction: 'BUY' or 'SELL'
            size: Position size
            stop_loss: Optional stop loss level
            take_profit: Optional take profit level
        
        Returns:
            Dict with order result
        """
        if not self.session_token:
            self.login()
        
        url = f"{self.base_url}/positions"
        headers = self._get_headers()
        
        payload = {
            'epic': epic,
            'direction': direction.upper(),
            'size': size,
            'guaranteedStop': False
        }
        
        if stop_loss:
            payload['stopLevel'] = stop_loss
        
        if take_profit:
            payload['profitLevel'] = take_profit
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code in [200, 201]:
                return {
                    'ok': True,
                    'dealReference': response.json().get('dealReference'),
                    'payload': payload,
                    'raw': response.json()
                }
            else:
                return {
                    'ok': False,
                    'error': f"Status {response.status_code}",
                    'payload': payload,
                    'raw': response.text
                }
                
        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
                'payload': payload
            }
    
    def close_position(self, deal_id: str) -> Dict[str, Any]:
        """Close an existing position"""
        if not self.session_token:
            self.login()
        
        url = f"{self.base_url}/positions/{deal_id}"
        headers = self._get_headers()
        
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            return {
                'ok': response.status_code == 200,
                'raw': response.json() if response.status_code == 200 else response.text
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for authenticated requests"""
        return {
            'X-CAP-API-KEY': self.api_key,
            'X-SECURITY-TOKEN': self.session_token or '',
            'CST': self.cst or '',
            'Content-Type': 'application/json'
        }


if __name__ == '__main__':
    # Test connection
    client = CapitalAPI()
    if client.login():
        print("✅ Login successful")
        info = client.get_account_info()
        if info:
            print(f"Account info: {info}")
    else:
        print("❌ Login failed")
