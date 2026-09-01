import json
import os
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import jsonschema

from scoring.scoring import score_ring
from graph.run import find_candidate_rings

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class CirceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="demo", **kwargs)

    def do_GET(self):
        if self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            return
        return super().do_GET()
        
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/rescore":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                payload = json.loads(post_data)
                investigator_invoices = payload.get("investigator_invoices", [])
                
                # Validate inputs against schema
                with open("contract/invoice.schema.json", "r", encoding="utf-8") as f:
                    invoice_schema = json.load(f)
                    
                # To validate, we wrap them in a mock object to match schema top-level if needed,
                # but the invoice schema applies to the top-level object containing "invoices"
                # wait, invoice.schema.json expects {"schema_version": 1, "invoices": [...]}
                validate_payload = {
                    "schema_version": 1,
                    "count": len(investigator_invoices),
                    "invoices": investigator_invoices
                }
                
                validator = jsonschema.Draft7Validator(invoice_schema)
                errors = list(validator.iter_errors(validate_payload))
                if errors:
                    error_msgs = [e.message for e in errors]
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Schema validation failed", "details": error_msgs}).encode("utf-8"))
                    return
                
                # Load entities and invoices
                with open("data/entities.json", "r", encoding="utf-8") as f:
                    ent_data = json.load(f)
                    entities_map = {e["id"]: e for e in ent_data["entities"]}
                    
                with open("data/invoices.json", "r", encoding="utf-8") as f:
                    inv_data = json.load(f)
                    all_invoices = inv_data["invoices"] + investigator_invoices
                    
                # Find candidate rings
                candidates = find_candidate_rings(entities_map, all_invoices, max_depth=8)
                
                # Score them
                scored = []
                for r in candidates:
                    scored.append(score_ring(r, all_invoices, entities_map))
                    
                # Sort and take top 50
                scored.sort(key=lambda r: r.get("expected_loss", 0), reverse=True)
                top_50 = scored[:50]
                
                response_data = {
                    "schema_version": 1,
                    "count": len(top_50),
                    "rings": top_50
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
                
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return
        
        self.send_response(404)
        self.end_headers()

def run(port=8098):
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, CirceHandler)
    print(f"Serving on port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, nargs="?", default=8098)
    args = parser.parse_args()
    run(args.port)
