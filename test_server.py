import urllib.request
import threading
import time
import sys
import os

# Import server directly since it's in the same directory
import server

def make_request():
    time.sleep(2)
    print("[Client] Sending GET request to http://localhost:8001/api/trackers...")
    try:
        with urllib.request.urlopen("http://localhost:8001/api/trackers", timeout=5) as response:
            print(f"[Client] Response Status: {response.status}")
            print(f"[Client] Response Content: {response.read().decode('utf-8')}")
    except Exception as e:
        print(f"[Client] Request failed: {e}")
        
    print("[Client] Sending POST request...")
    try:
        import json
        data = json.dumps({"name": "Test", "keyword": "test", "discount": 20}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8001/api/trackers",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"[Client] POST Response Status: {response.status}")
            print(f"[Client] POST Response Content: {response.read().decode('utf-8')}")
    except Exception as e:
        print(f"[Client] POST failed: {e}")

if __name__ == "__main__":
    # Run server on port 8001 to avoid conflicts
    server_address = ("", 8001)
    from http.server import HTTPServer
    httpd = HTTPServer(server_address, server.DealSpyAPIHandler)
    
    # Start request thread
    client_thread = threading.Thread(target=make_request)
    client_thread.start()
    
    # Start background scanner thread (from server.py)
    scanner_thread = threading.Thread(target=server.background_scanner_loop, daemon=True)
    scanner_thread.start()
    
    print("[Server] Starting server on port 8001...")
    # Serve one request or run for 10 seconds
    httpd.timeout = 8
    httpd.handle_request() # handle first GET
    httpd.handle_request() # handle second POST
    
    print("[Server] Shutting down.")
    httpd.server_close()
    client_thread.join()
