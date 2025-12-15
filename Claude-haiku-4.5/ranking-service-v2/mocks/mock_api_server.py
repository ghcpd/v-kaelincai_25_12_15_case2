#!/usr/bin/env python
"""
Mock API Server for Ranking Service v2
- Simulates /api/v2/rank endpoint
- Supports immediate, pending, and delayed responses
- Useful for client integration testing
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from api_handler import get_ranking_service
from observability import get_request_logger, configure_logging


class RankingAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for ranking API."""
    
    def do_POST(self):
        """Handle POST requests to /api/v2/rank."""
        if self.path == '/api/v2/rank':
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                request_data = json.loads(body)
            except json.JSONDecodeError:
                self._send_error_response(400, "Invalid JSON in request body")
                return
            
            # Process ranking request
            service = get_ranking_service()
            response_data, status_code = service.process_request(request_data)
            
            # Send response
            self._send_json_response(response_data, status_code)
        
        elif self.path.startswith('/api/v2/health'):
            # Health check endpoint
            self._send_json_response({"status": "healthy"}, 200)
        
        else:
            self._send_error_response(404, "Not found")
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/api/v2/health':
            self._send_json_response({"status": "healthy"}, 200)
        elif self.path == '/api/v2/metrics':
            service = get_ranking_service()
            metrics = service.get_metrics()
            self._send_json_response(metrics, 200)
        else:
            self._send_error_response(404, "Not found")
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def _send_error_response(self, status_code: int, message: str):
        """Send error response."""
        error_data = {
            "status": "error",
            "error_code": f"HTTP_{status_code}",
            "error_message": message
        }
        self._send_json_response(error_data, status_code)
    
    def log_message(self, format, *args):
        """Suppress default logging (use structured logging instead)."""
        pass


def run_server(port: int = 8000):
    """Run the mock API server."""
    # Configure logging
    configure_logging(log_file=os.path.join(
        os.path.dirname(__file__),
        'logs',
        'mock_api.log'
    ))
    
    logger = get_request_logger()
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, RankingAPIHandler)
    
    print(f"Starting Ranking Service v2 Mock API on http://0.0.0.0:{port}")
    print("Endpoints:")
    print(f"  POST http://localhost:{port}/api/v2/rank")
    print(f"  GET  http://localhost:{port}/api/v2/health")
    print(f"  GET  http://localhost:{port}/api/v2/metrics")
    print("")
    print("Example curl request:")
    print(f"""curl -X POST http://localhost:{port}/api/v2/rank \\
  -H "Content-Type: application/json" \\
  -d '{{"request_id": "test-1", "students": [{{"name": "Alice", "score": 95}}, {{"name": "Bob", "score": 95}}]}}'""")
    print("")
    print("Press Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
