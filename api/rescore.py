
import json
import os
import jsonschema
from http.server import BaseHTTPRequestHandler

# Import modules from the root (Vercel adds the project root to sys.path)
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.scoring import score_ring
from graph.run import find_candidate_rings

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data)
            investigator_invoices = payload.get("investigator_invoices", [])
            
            # Use absolute paths for Vercel
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            schema_path = os.path.join(root_dir, "contract", "invoice.schema.json")
            entities_path = os.path.join(root_dir, "data", "entities.json")
            invoices_path = os.path.join(root_dir, "data", "invoices.json")
            
            # Validate inputs against schema
            with open(schema_path, "r", encoding="utf-8") as f:
                invoice_schema = json.load(f)
                
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
            with open(entities_path, "r", encoding="utf-8") as f:
                ent_data = json.load(f)
                entities_map = {e["id"]: e for e in ent_data["entities"]}
                
            with open(invoices_path, "r", encoding="utf-8") as f:
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
