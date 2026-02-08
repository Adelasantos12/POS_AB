#!/usr/bin/env python3
"""
Backend Testing Suite for Adelé POS Django System
Tests all Django views and API endpoints
"""

import requests
import sys
import json
from datetime import datetime

class DjangoPOSTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.csrf_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_user_id = None
        
    def get_csrf_token(self):
        """Get CSRF token from Django"""
        try:
            response = self.session.get(f"{self.base_url}/login/")
            if response.status_code == 200:
                # Extract CSRF token from cookies
                self.csrf_token = self.session.cookies.get('csrftoken')
                return True
        except Exception as e:
            print(f"❌ Failed to get CSRF token: {e}")
        return False

    def run_test(self, name, method, endpoint, expected_status, data=None, follow_redirects=False):
        """Run a single test"""
        url = f"{self.base_url}{endpoint}"
        headers = {}
        
        if self.csrf_token:
            headers['X-CSRFToken'] = self.csrf_token
            
        if data and method == 'POST':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, allow_redirects=follow_redirects)
            elif method == 'POST':
                if isinstance(data, dict):
                    response = self.session.post(url, data=data, headers=headers, allow_redirects=follow_redirects)
                else:
                    headers['Content-Type'] = 'application/json'
                    response = self.session.post(url, data=data, headers=headers, allow_redirects=follow_redirects)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                if 'Location' in response.headers:
                    print(f"   Redirected to: {response.headers['Location']}")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.text:
                    print(f"   Response: {response.text[:200]}...")

            return success, response

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, None

    def test_terminal_login(self):
        """Test terminal login with adela.santos12/Karinakakapopo1"""
        print("\n=== TESTING TERMINAL LOGIN ===")
        
        # Get CSRF token first
        if not self.get_csrf_token():
            return False
            
        # Test login page access
        success, response = self.run_test(
            "Login page access",
            "GET", 
            "/login/",
            200
        )
        
        if not success:
            return False
            
        # Test login with Adela Santos credentials
        login_data = {
            'username': 'adela.santos12',
            'password': 'Karinakakapopo1',
            'csrfmiddlewaretoken': self.csrf_token
        }
        
        success, response = self.run_test(
            "Terminal login with adela.santos12/Karinakakapopo1",
            "POST",
            "/login/",
            302,  # Should redirect after successful login
            data=login_data,
            follow_redirects=False
        )
        
        return success

    def test_profile_selection(self):
        """Test profile selection screen"""
        print("\n=== TESTING PROFILE SELECTION ===")
        
        success, response = self.run_test(
            "Profile selection screen",
            "GET",
            "/perfiles/",
            200
        )
        
        if success and response:
            # Check if expected users are in the response
            content = response.text.lower()
            expected_users = ['adela', 'ceo', 'vendedora']
            found_users = []
            
            for user in expected_users:
                if user in content:
                    found_users.append(user)
                    
            if len(found_users) >= 2:
                print(f"✅ Found expected users: {found_users}")
                # Extract user ID for Adela Santos (simple parsing)
                import re
                user_id_matches = re.findall(r'user_id=(\d+)', response.text)
                if user_id_matches:
                    self.admin_user_id = user_id_matches[0]  # Use first user ID found
                    print(f"✅ User ID for testing: {self.admin_user_id}")
            else:
                print(f"⚠️  Expected users not found. Found: {found_users}")
                print("   Expected: Adela, CEO, María Vendedora")
        
        return success

    def test_profile_authentication(self):
        """Test profile authentication with admin password"""
        print("\n=== TESTING PROFILE AUTHENTICATION ===")
        
        if not self.admin_user_id:
            print("❌ Admin user ID not found, skipping profile auth test")
            return False
            
        # Test GET authentication page
        success, response = self.run_test(
            "Profile authentication page",
            "GET",
            f"/perfiles/autenticar/?user_id={self.admin_user_id}",
            200
        )
        
        if not success:
            return False
            
        # Update CSRF token from the authentication page
        if response and 'csrfmiddlewaretoken' in response.text:
            import re
            csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.text)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
                print(f"✅ Updated CSRF token from auth page")
            
        # Test POST authentication with Adela Santos password
        auth_data = {
            'user_id': self.admin_user_id,
            'password': 'Karinakakapopo1',
            'csrfmiddlewaretoken': self.csrf_token
        }
        
        success, response = self.run_test(
            "Profile authentication with Karinakakapopo1",
            "POST",
            "/perfiles/autenticar/",
            302,  # Should redirect to dashboard
            data=auth_data
        )
        
        if success:
            print("✅ Profile authentication successful")
            # Follow the redirect to complete the authentication
            if response and 'Location' in response.headers:
                redirect_url = response.headers['Location']
                if redirect_url.startswith('/'):
                    redirect_url = redirect_url
                success2, response2 = self.run_test(
                    "Follow authentication redirect",
                    "GET",
                    redirect_url,
                    200
                )
                return success2
        
        return success

    def test_admin_dashboard(self):
        """Test admin dashboard access"""
        print("\n=== TESTING ADMIN DASHBOARD ===")
        
        success, response = self.run_test(
            "Admin dashboard access",
            "GET",
            "/dashboard/",
            200
        )
        
        if success and response:
            # Check for key dashboard elements
            content = response.text.lower()
            if 'dashboard' in content and ('kpi' in content or 'ventas' in content or 'gráfico' in content):
                print("✅ Dashboard contains expected elements")
            else:
                print("⚠️  Dashboard may be missing key elements")
        
        return success

    def test_user_management(self):
        """Test user management panel"""
        print("\n=== TESTING USER MANAGEMENT ===")
        
        success, response = self.run_test(
            "User management list",
            "GET",
            "/usuarios/",
            200
        )
        
        if success and response:
            content = response.text.lower()
            if 'usuarios' in content or 'personal' in content:
                print("✅ User management page loaded")
                
                # Check for admin user in the list
                if 'admin' in content:
                    print("✅ Admin user visible in user list")
                else:
                    print("⚠️  Admin user not visible in user list")
            else:
                print("⚠️  User management page may not have loaded correctly")
        
        return success

    def test_user_editing(self):
        """Test user editing functionality"""
        print("\n=== TESTING USER EDITING ===")
        
        if not self.admin_user_id:
            print("❌ Admin user ID not found, skipping user edit test")
            return False
            
        success, response = self.run_test(
            "User edit page",
            "GET",
            f"/usuarios/editar/{self.admin_user_id}/",
            200
        )
        
        if success and response:
            content = response.text.lower()
            if 'editar' in content and ('roles' in content or 'permisos' in content):
                print("✅ User edit page contains expected elements")
            else:
                print("⚠️  User edit page may be missing key elements")
        
        return success

    def test_user_history(self):
        """Test user history functionality"""
        print("\n=== TESTING USER HISTORY ===")
        
        if not self.admin_user_id:
            print("❌ Admin user ID not found, skipping user history test")
            return False
            
        success, response = self.run_test(
            "User history page",
            "GET",
            f"/usuarios/historial/{self.admin_user_id}/",
            200
        )
        
        if success and response:
            content = response.text.lower()
            if 'historial' in content:
                print("✅ User history page loaded")
            else:
                print("⚠️  User history page may not have loaded correctly")
        
        return success

    def test_cash_register_opening(self):
        """Test cash register opening"""
        print("\n=== TESTING CASH REGISTER OPENING ===")
        
        success, response = self.run_test(
            "Cash register opening page",
            "GET",
            "/caja/apertura/",
            200
        )
        
        if success and response:
            content = response.text.lower()
            if 'apertura' in content and 'caja' in content:
                print("✅ Cash register opening page loaded")
            else:
                print("⚠️  Cash register opening page may not have loaded correctly")
        
        return success

    def test_export_functionality(self):
        """Test export functionality"""
        print("\n=== TESTING EXPORT FUNCTIONALITY ===")
        
        # Test CSV inventory export
        success1, response1 = self.run_test(
            "Export inventory CSV",
            "GET",
            "/exportar/inventario/csv/",
            200
        )
        
        if success1 and response1:
            if response1.headers.get('Content-Type') == 'text/csv':
                print("✅ CSV export returns correct content type")
            else:
                print("⚠️  CSV export may not return correct content type")
        
        # Test Excel inventory export
        success2, response2 = self.run_test(
            "Export inventory Excel",
            "GET",
            "/exportar/inventario/excel/",
            200
        )
        
        if success2 and response2:
            content_type = response2.headers.get('Content-Type', '')
            if 'spreadsheet' in content_type or 'excel' in content_type:
                print("✅ Excel export returns correct content type")
            else:
                print("⚠️  Excel export may not return correct content type")
        
        # Test PDF sales export
        success3, response3 = self.run_test(
            "Export sales PDF",
            "GET",
            "/exportar/ventas/pdf/",
            200
        )
        
        if success3 and response3:
            if response3.headers.get('Content-Type') == 'application/pdf':
                print("✅ PDF export returns correct content type")
            else:
                print("⚠️  PDF export may not return correct content type")
        
        return success1 and success2 and success3

    def test_api_endpoints(self):
        """Test API endpoints"""
        print("\n=== TESTING API ENDPOINTS ===")
        
        # Test duplicate detection API
        duplicate_data = json.dumps({
            'categoria': 'Vestido',
            'rasgo1': 'Manga Larga',
            'rasgo2': 'Satinado',
            'color': 'Rosa Palo',
            'talla': 'M'
        })
        success1, response1 = self.run_test(
            "Check duplicates API",
            "POST",
            "/api/check-duplicados/",
            200,
            data=duplicate_data
        )
        
        if success1 and response1:
            try:
                result = response1.json()
                if 'duplicados' in result:
                    print("✅ Check duplicates API returns expected structure")
                else:
                    print("⚠️  Check duplicates API may not return expected structure")
            except:
                print("⚠️  Check duplicates API response is not valid JSON")
        
        # Test product validation API
        product_data = json.dumps({
            'categoria': 'Top',
            'rasgo1': 'Corto',
            'rasgo2': 'Algodón',
            'color': 'Blanco',
            'talla': 'S',
            'precio': 299
        })
        success2, response2 = self.run_test(
            "Validate create product API",
            "POST",
            "/api/validar-crear-producto/",
            200,
            data=product_data
        )
        
        if success2 and response2:
            try:
                result = response2.json()
                if 'status' in result:
                    print("✅ Validate create product API returns expected structure")
                else:
                    print("⚠️  Validate create product API may not return expected structure")
            except:
                print("⚠️  Validate create product API response is not valid JSON")
        
        # Test printer verification API
        success3, response3 = self.run_test(
            "Printer verification API",
            "GET",
            "/api/verificar-impresora/",
            200
        )
        
        if success3 and response3:
            try:
                result = response3.json()
                if 'conectada' in result:
                    print("✅ Printer verification API returns expected structure")
                    if not result['conectada']:
                        print("ℹ️  Printer not connected (expected for testing)")
                else:
                    print("⚠️  Printer verification API may not return expected structure")
            except:
                print("⚠️  Printer verification API response is not valid JSON")
        
        # Test AI strategy API (mocked)
        ai_data = json.dumps({})
        success4, response4 = self.run_test(
            "AI Strategy API",
            "POST",
            "/api/ai-strategy/",
            200,
            data=ai_data
        )
        
        if success4 and response4:
            try:
                result = response4.json()
                if 'estrategia' in result:
                    print("✅ AI Strategy API returns expected data")
                else:
                    print("⚠️  AI Strategy API may not return expected data")
            except:
                print("⚠️  AI Strategy API response is not valid JSON")
        
        # Test product search API
        success5, response5 = self.run_test(
            "Product search API",
            "GET",
            "/api/search-productos/?q=vestido",
            200
        )
        
        if success5 and response5:
            try:
                result = response5.json()
                if 'results' in result:
                    print("✅ Product search API returns expected structure")
                else:
                    print("⚠️  Product search API may not return expected structure")
            except:
                print("⚠️  Product search API response is not valid JSON")
        
        return success1 and success2 and success3 and success4 and success5

def main():
    print("🚀 Starting Adelé POS Django Backend Tests")
    print("=" * 50)
    
    tester = DjangoPOSTester()
    
    # Run all tests
    tests = [
        tester.test_terminal_login,
        tester.test_profile_selection,
        tester.test_profile_authentication,
        tester.test_admin_dashboard,
        tester.test_user_management,
        tester.test_user_editing,
        tester.test_user_history,
        tester.test_cash_register_opening,
        tester.test_export_functionality,
        tester.test_api_endpoints
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 FINAL RESULTS")
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Success rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "0%")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())