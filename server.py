import os
import re
import json
import uuid
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

import threading

# Directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
TRACKERS_FILE = os.path.join(DATA_DIR, "trackers.json")
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PUBLIC_DIR, exist_ok=True)

# Lock for thread safety
db_lock = threading.RLock()

# Helper: Load/Save JSON
def load_json(filepath, default):
    with db_lock:
        if not os.path.exists(filepath):
            return default
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

def save_json(filepath, data):
    with db_lock:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving to {filepath}: {e}")

# Global In-Memory State
trackers = load_json(TRACKERS_FILE, [])
deals = load_json(DEALS_FILE, [])

# Ensure all trackers have standard structure
for tracker in trackers:
    if "last_scan" not in tracker:
        tracker["last_scan"] = 0
    if "market_price" not in tracker:
        tracker["market_price"] = 0.0

# ----------------- eBay Scraper Logic -----------------

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def http_get(url):
    """Perform a web request with standard headers."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Error fetching url {url}: {e}")
        return ""

def parse_price(price_str):
    """Extract a float price value from a string like '$1,234.56'."""
    if not price_str:
        return 0.0
    # Find the first number pattern like 1,234.56
    match = re.search(r"([0-9,]+\.[0-9]{2})", price_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0

def parse_shipping(shipping_str):
    """Extract shipping cost or return 0.0 if free/not listed."""
    if not shipping_str:
        return 0.0
    s_lower = shipping_str.lower()
    if "free" in s_lower:
        return 0.0
    match = re.search(r"\+?\$([0-9,]+\.[0-9]{2})", shipping_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0

def parse_ebay_html(html):
    """Parse listing items from eBay search result HTML using regex."""
    items = []
    # Split the HTML page by the standard s-item class wrapper
    chunks = html.split('class="s-item__wrapper')
    if len(chunks) <= 1:
        # Fallback to alternative class
        chunks = html.split('class="s-item ')
        
    # First chunk is the header/metadata, discard it
    for chunk in chunks[1:]:
        # Extract title
        title_match = re.search(r'class="s-item__title"[^>]*>(?:<span[^>]*>.*?<\/span>)?(?:<span[^>]*>NEW LISTING<\/span>\s*)?([^<]+)', chunk)
        if not title_match:
            # Fallback for alternative structures
            title_match = re.search(r'class="s-item__title"[^>]*>.*?<span>([^<]+)', chunk)
        title = title_match.group(1).strip() if title_match else "Unknown Item"
        if title.lower() in ("shop on ebay", "brand new", "s-item__title"):
            continue # Ignore dummy eBay placeholders
            
        # Extract link
        link_match = re.search(r'href="([^"]+)"[^>]*class="s-item__link"', chunk)
        if not link_match:
            link_match = re.search(r'class="s-item__link"[^>]+href="([^"]+)"', chunk)
        link = link_match.group(1) if link_match else ""
        # Clean eBay referral params from link
        if link:
            link = link.split("?")[0]
            
        # Extract price
        price_match = re.search(r'class="s-item__price"[^>]*>.*?\$([0-9,]+\.[0-9]{2})', chunk)
        price = float(price_match.group(1).replace(",", "")) if price_match else 0.0
        
        # Extract shipping
        shipping_match = re.search(r'class="(?:s-item__shipping|s-item__logisticsCost)"[^>]*>([^<]+)', chunk)
        shipping_str = shipping_match.group(1).strip() if shipping_match else "Free shipping"
        shipping = parse_shipping(shipping_str)
        
        # Extract image
        image_match = re.search(r'src="([^"]+)"[^>]+class="s-item__image-img"', chunk)
        if not image_match:
            image_match = re.search(r'class="s-item__image-img"[^>]+src="([^"]+)"', chunk)
        if not image_match:
            image_match = re.search(r'data-src="([^"]+)"[^>]+class="s-item__image-img"', chunk)
        image = image_match.group(1) if image_match else ""
        if "gif" in image or "1x1" in image:
            image = "" # Avoid placeholders
            
        if price > 0:
            items.append({
                "title": title,
                "price": price,
                "shipping": shipping,
                "total": price + shipping,
                "url": link,
                "image": image
            })
    return items

def calculate_market_price(sold_items):
    """Calculate the market median price using IQR (Interquartile Range) outlier filtering."""
    if not sold_items:
        return 0.0, []
        
    totals = sorted([item["total"] for item in sold_items])
    n = len(totals)
    
    # Calculate IQR to filter out outlier listings (like accessories or bundle lots)
    if n >= 4:
        q1 = totals[int(n * 0.25)]
        q3 = totals[int(n * 0.75)]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Filter sold listings
        filtered_items = [item for item in sold_items if lower_bound <= item["total"] <= upper_bound]
    else:
        filtered_items = sold_items
        
    if not filtered_items:
        filtered_items = sold_items
        
    # Calculate median of filtered items
    filtered_totals = sorted([item["total"] for item in filtered_items])
    fn = len(filtered_totals)
    if fn % 2 == 1:
        median = filtered_totals[fn // 2]
    else:
        median = (filtered_totals[fn // 2 - 1] + filtered_totals[fn // 2]) / 2.0
        
    return round(median, 2), filtered_items

# ----------------- Mock Generator Logic -----------------

def get_base_mock_price(keyword):
    """Estimate a realistic market price based on typical high-value items."""
    k = keyword.lower()
    if "4090" in k: return 1600.0
    if "4080" in k: return 1000.0
    if "4070" in k: return 550.0
    if "iphone 15 pro" in k: return 850.0
    if "iphone 15" in k: return 650.0
    if "iphone 14" in k: return 500.0
    if "ps5" in k or "playstation 5" in k: return 350.0
    if "switch oled" in k: return 220.0
    if "wh-1000xm5" in k or "xm5" in k: return 230.0
    if "steam deck" in k: return 300.0
    if "macbook air m1" in k: return 450.0
    if "macbook air m2" in k: return 650.0
    if "ipad pro" in k: return 600.0
    return 120.0 # Default fallback

def generate_mock_sold_items(keyword):
    """Generate 20-30 realistic sold listings with slight price variations and some outliers."""
    import random
    base = get_base_mock_price(keyword)
    sold_items = []
    
    # 25 normal listings
    for i in range(25):
        # price variations within +/- 12%
        price = base * random.uniform(0.88, 1.12)
        shipping = random.choice([0.0, 5.0, 9.99, 12.50, 15.00])
        price = round(price - shipping, 2)
        sold_items.append({
            "title": f"Excellent {keyword} - Condition {random.choice(['Mint', 'Good', 'Like New'])}",
            "price": price,
            "shipping": shipping,
            "total": price + shipping,
            "url": "https://www.ebay.com/itm/mock-sold-listing",
            "image": "https://picsum.photos/200/150?random=" + str(random.randint(1, 1000))
        })
        
    # Add a few outliers (accessory like charger/box, or a bulk lot bundle)
    # 1. Low price accessory outlier
    sold_items.append({
        "title": f"OEM Charger / Box for {keyword} (ACCESSORY ONLY)",
        "price": round(base * 0.08, 2),
        "shipping": 4.99,
        "total": round(base * 0.08 + 4.99, 2),
        "url": "https://www.ebay.com/itm/mock-sold-outlier-low",
        "image": ""
    })
    # 2. High price bundle outlier
    sold_items.append({
        "title": f"BULK LOT: 3x {keyword} Bundle Dealer Refurbished",
        "price": round(base * 2.8, 2),
        "shipping": 25.00,
        "total": round(base * 2.8 + 25.00, 2),
        "url": "https://www.ebay.com/itm/mock-sold-outlier-high",
        "image": ""
    })
    
    return sold_items

def generate_mock_active_items(keyword, market_price, trigger_deal=False):
    """Generate active items. If trigger_deal is True, inject an underpriced listing."""
    import random
    base = market_price if market_price > 0 else get_base_mock_price(keyword)
    active = []
    
    # 3-5 normal active listings
    for i in range(random.randint(3, 5)):
        # price close to market price
        price = base * random.uniform(0.95, 1.08)
        shipping = random.choice([0.0, 7.99, 12.00])
        price = round(price - shipping, 2)
        active.append({
            "title": f"Genuine {keyword} - Tested & Functional",
            "price": price,
            "shipping": shipping,
            "total": price + shipping,
            "url": "https://www.ebay.com/itm/mock-active-listing",
            "image": "https://picsum.photos/200/150?random=" + str(random.randint(1, 1000))
        })
        
    if trigger_deal:
        # Generate a listing that is 22% - 40% below market value!
        discount = random.uniform(0.22, 0.40)
        total = base * (1.0 - discount)
        shipping = random.choice([0.0, 5.0, 9.99])
        price = round(total - shipping, 2)
        active.append({
            "title": f"[BARGAIN] {keyword} - Quick Sale Must Go!",
            "price": price,
            "shipping": shipping,
            "total": price + shipping,
            "url": "https://www.ebay.com/itm/mock-active-deal",
            "image": "https://picsum.photos/200/150?random=" + str(random.randint(1, 1000))
        })
        
    return active

# ----------------- Unified Scan Engine -----------------

def run_tracker_scan(tracker, trigger_deal=False):
    """Run full scan (calculate market price + scan active listings) for a tracker."""
    keyword = tracker["keyword"]
    mode = tracker.get("mode", "mock")
    discount_threshold = tracker.get("discount", 20.0)
    
    print(f"Scanning tracker '{tracker['name']}' ({keyword}) in {mode} mode...")
    
    sold_items = []
    active_items = []
    
    if mode == "live":
        # 1. Fetch Sold Listings to establish Market Price
        sold_url = f"https://www.ebay.com/sch/i.html?_nkw={urllib.parse.quote(keyword)}&LH_Sold=1&LH_Complete=1&_ipg=60"
        html = http_get(sold_url)
        if html:
            sold_items = parse_ebay_html(html)
            
        # 2. Fetch Active Listings
        active_url = f"https://www.ebay.com/sch/i.html?_nkw={urllib.parse.quote(keyword)}&_sop=10"
        html_active = http_get(active_url)
        if html_active:
            active_items = parse_ebay_html(html_active)
    else:
        # Mock mode
        sold_items = generate_mock_sold_items(keyword)
        # Randomly choose whether this scan yields a deal (always true if triggered manually)
        has_deal = trigger_deal or (time.time() % 3 < 1)
        active_items = generate_mock_active_items(keyword, get_base_mock_price(keyword), has_deal)
        
    # Calculate market median & filtered listings
    market_price, filtered_solds = calculate_market_price(sold_items)
    
    # Update tracker stats
    tracker["market_price"] = market_price
    tracker["last_scan"] = int(time.time())
    
    # Find deals in active listings
    new_deals_found = []
    if market_price > 0:
        for item in active_items:
            total = item["total"]
            # Check if listing price is significantly below market price
            if total < market_price:
                discount_pct = round(((market_price - total) / market_price) * 100, 1)
                if discount_pct >= discount_threshold:
                    deal_id = str(uuid.uuid4())
                    new_deal = {
                        "id": deal_id,
                        "tracker_id": tracker["id"],
                        "tracker_name": tracker["name"],
                        "keyword": keyword,
                        "title": item["title"],
                        "price": item["price"],
                        "shipping": item["shipping"],
                        "total": total,
                        "market_price": market_price,
                        "discount_pct": discount_pct,
                        "url": item["url"],
                        "image": item.get("image", ""),
                        "timestamp": int(time.time())
                    }
                    new_deals_found.append(new_deal)
                    
    # Sync new deals to global database (avoid duplicates by checking title + price)
    global deals
    with db_lock:
        deals_added = False
        for nd in new_deals_found:
            # Check duplicate
            duplicate = any(
                d["tracker_id"] == nd["tracker_id"] and 
                d["title"] == nd["title"] and 
                abs(d["total"] - nd["total"]) < 0.05
                for d in deals
            )
            if not duplicate:
                deals.insert(0, nd) # Add to top
                deals_added = True
                
        # Limit total deals saved to 100 to save space
        if len(deals) > 100:
            deals = deals[:100]
            
        if deals_added:
            save_json(DEALS_FILE, deals)
            
    # Save trackers state
    save_json(TRACKERS_FILE, trackers)
    
    return {
        "market_price": market_price,
        "sold_count": len(sold_items),
        "filtered_sold_count": len(filtered_solds),
        "active_count": len(active_items),
        "deals_found": len(new_deals_found),
        "sold_listings": sold_items, # returned for graphing
    }

# Background thread runner
def background_scanner_loop():
    print("Background scanner worker thread started.")
    while True:
        try:
            # Check all trackers. Scan if interval elapsed (default 300s / 5mins)
            now = int(time.time())
            with db_lock:
                trackers_copy = list(trackers)
                
            for tracker in trackers_copy:
                interval = tracker.get("interval", 300)
                last_scan = tracker.get("last_scan", 0)
                if now - last_scan >= interval:
                    # Scan (do not force a mock deal in background to keep it realistic)
                    run_tracker_scan(tracker, trigger_deal=False)
        except Exception as e:
            print(f"Error in background scanner: {e}")
        time.sleep(15) # Wake up every 15 seconds to poll tracker schedules

# ----------------- HTTP Server Handler -----------------

class DealSpyAPIHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Silence standard HTTP access logging to prevent cluttering output
        pass

    def send_json(self, status_code, data):
        json_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(json_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json_bytes)

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        
        # API Routes
        if path == "/api/trackers":
            self.send_json(200, trackers)
            return
            
        elif path == "/api/deals":
            self.send_json(200, deals)
            return
            
        # Static files fallback
        # Normalize relative path
        rel_path = path.lstrip("/")
        if not rel_path or rel_path == "":
            rel_path = "index.html"
            
        file_path = os.path.join(PUBLIC_DIR, rel_path)
        
        # Security check: ensure path is within public folder
        if not os.path.abspath(file_path).startswith(os.path.abspath(PUBLIC_DIR)):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"403 Forbidden")
            return
            
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Resolve content type
            content_type = "text/plain"
            if file_path.endswith(".html"):
                content_type = "text/html"
            elif file_path.endswith(".css"):
                content_type = "text/css"
            elif file_path.endswith(".js"):
                content_type = "application/javascript"
            elif file_path.endswith(".json"):
                content_type = "application/json"
            elif file_path.endswith(".png"):
                content_type = "image/png"
            elif file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
                content_type = "image/jpeg"
            elif file_path.endswith(".ico"):
                content_type = "image/x-icon"
                
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"500 Internal Error: {e}".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        
        # Read content body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        
        if path == "/api/trackers":
            try:
                data = json.loads(body)
            except Exception:
                self.send_json(400, {"error": "Invalid JSON payload"})
                return
                
            name = data.get("name", "").strip()
            keyword = data.get("keyword", "").strip()
            discount = float(data.get("discount", 20.0))
            mode = data.get("mode", "mock").strip()
            interval = int(data.get("interval", 300))
            
            if not name or not keyword:
                self.send_json(400, {"error": "Name and Keyword are required"})
                return
                
            new_tracker = {
                "id": str(uuid.uuid4()),
                "name": name,
                "keyword": keyword,
                "discount": discount,
                "mode": mode,
                "interval": interval,
                "last_scan": 0,
                "market_price": 0.0
            }
            
            with db_lock:
                trackers.append(new_tracker)
                save_json(TRACKERS_FILE, trackers)
                
            self.send_json(201, new_tracker)
            return
            
        elif path.startswith("/api/trackers/") and path.endswith("/scan"):
            # Format: /api/trackers/<id>/scan
            tracker_id = path.split("/")[3]
            tracker = next((t for t in trackers if t["id"] == tracker_id), None)
            
            if not tracker:
                self.send_json(404, {"error": "Tracker not found"})
                return
                
            # Perform scan immediately (forces a mock deal if in mock mode to verify functionality)
            try:
                scan_results = run_tracker_scan(tracker, trigger_deal=True)
                self.send_json(200, {
                    "success": True,
                    "tracker": tracker,
                    "results": scan_results
                })
            except Exception as e:
                self.send_json(500, {"error": f"Scan failed: {str(e)}"})
            return
            
        self.send_json(404, {"error": "Endpoint not found"})

    def do_DELETE(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        
        if path.startswith("/api/trackers/"):
            tracker_id = path.split("/")[3]
            global trackers, deals
            
            with db_lock:
                # Find index
                index = next((i for i, t in enumerate(trackers) if t["id"] == tracker_id), -1)
                if index == -1:
                    self.send_json(404, {"error": "Tracker not found"})
                    return
                # Remove
                removed = trackers.pop(index)
                save_json(TRACKERS_FILE, trackers)
                
                # Delete corresponding deals to clean up feed
                deals = [d for d in deals if d["tracker_id"] != tracker_id]
                save_json(DEALS_FILE, deals)
                
            self.send_json(200, {"success": True, "message": f"Deleted tracker '{removed['name']}'"})
            return
            
        self.send_json(404, {"error": "Endpoint not found"})

# ----------------- Start Server -----------------

def run(port=8000):
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, DealSpyAPIHandler)
    print(f"DealSpy Web App running on http://localhost:{port}")
    
    # Start background scanner thread
    scanner_thread = threading.Thread(target=background_scanner_loop, daemon=True)
    scanner_thread.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    run(8000)
