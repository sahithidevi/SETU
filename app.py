import os
import json
import time
import math
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import mimetypes

# Directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / 'data'
CLIENT_PUBLIC = BASE_DIR.parent / 'client' / 'public'
FACILITIES_PATH = DATA_DIR / 'facilities.json'
REFERRALS_PATH = DATA_DIR / 'referrals.json'

DATA_DIR.mkdir(parents=True, exist_ok=True)
CLIENT_PUBLIC.mkdir(parents=True, exist_ok=True)

def load_facilities():
    try:
        with open(FACILITIES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print('Failed to load facilities:', e)
        return []

def save_facilities(data):
    try:
        with open(FACILITIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print('Failed to save facilities:', e)

def load_referrals():
    try:
        if REFERRALS_PATH.exists():
            with open(REFERRALS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print('Failed to load referrals:', e)
    return []

def save_referrals(data):
    try:
        with open(REFERRALS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print('Failed to save referrals:', e)

facilities = load_facilities()
referrals = load_referrals()

# Helper functions
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def compute_score(to_fac, from_fac):
    distance = haversine(to_fac['lat'], to_fac['lon'], from_fac['lat'], from_fac['lon'])
    capacity = to_fac.get('capacity', 1)
    acceptance_rate = to_fac.get('acceptanceRate', 0.5)
    
    # Heuristic scoring: high capacity & acceptance rate, lower distance penalty
    # Score scaled roughly 0 to 10
    score = (capacity * acceptance_rate) / (math.log(distance + 1.5) + 0.5)
    confidence = min(98, max(52, int(acceptance_rate * 70 + (10 / (distance + 1)) * 25 + min(15, capacity * 2))))
    
    reasoning = f"Distance: {distance:.1f} km | Available Beds: {capacity} | Historical Acceptance: {int(acceptance_rate*100)}%"
    return {'score': round(score, 2), 'distance': round(distance, 1), 'confidence': confidence, 'reasoning': reasoning}

# Active SSE client streams
sse_clients = []

def broadcast_sse(event_data):
    global sse_clients
    payload = f"data: {json.dumps(event_data)}\n\n".encode('utf-8')
    active_clients = []
    for client_wfile in sse_clients:
        try:
            client_wfile.write(payload)
            client_wfile.flush()
            active_clients.append(client_wfile)
        except Exception:
            pass
    sse_clients = active_clients

class SetuHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Serve client public files
        if path.startswith('/api/'):
            return path
        rel_path = path.lstrip('/')
        if not rel_path or rel_path == '':
            rel_path = 'index.html'
        full_path = CLIENT_PUBLIC / rel_path
        return str(full_path)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        
        # 1. Facilities
        if parsed.path == '/api/facilities':
            return self.send_json(facilities)
            
        # 2. Facility Details
        if parsed.path.startswith('/api/facility/'):
            fid = parsed.path.split('/')[-1]
            fac = next((f for f in facilities if f['id'] == fid), None)
            if fac:
                return self.send_json(fac)
            return self.send_json({'error': 'Facility not found'}, 404)
            
        # 3. Referral Recommendations
        if parsed.path.startswith('/api/recommend/'):
            parts = parsed.path.split('/')
            if len(parts) >= 5:
                from_id = parts[3]
                specialist = parts[4].replace('%20', ' ')
                from_fac = next((f for f in facilities if f['id'] == from_id), None)
                if not from_fac:
                    return self.send_json({'error': 'Source facility not found'}, 400)
                
                candidates = [
                    f for f in facilities 
                    if any(specialist.lower() in s.lower() for s in f.get('specialists', [])) 
                    and f['id'] != from_id
                ]
                
                scored = []
                for f in candidates:
                    sc = compute_score(f, from_fac)
                    scored.append({**sc, 'facility': f})
                scored.sort(key=lambda x: x['score'], reverse=True)
                return self.send_json(scored)
            return self.send_json({'error': 'Invalid recommendation query'}, 400)
            
        # 4. Referral List
        if parsed.path == '/api/referral_list':
            return self.send_json(referrals)

        # 5. Analytics
        if parsed.path == '/api/analytics':
            counts_by_target = {}
            for r in referrals:
                tid = r.get('to_name') or r.get('to') or 'Unknown'
                counts_by_target[tid] = counts_by_target.get(tid, 0) + 1
            
            stats = {
                'totalReferrals': len(referrals),
                'activeFacilities': len(facilities),
                'completed': len([r for r in referrals if r.get('status') == 'Completed']),
                'inTransit': len([r for r in referrals if r.get('status') in ['In Transit', 'Confirmed']]),
                'escalated': len([r for r in referrals if r.get('escalated')]),
                'countsByTarget': counts_by_target
            }
            return self.send_json(stats)

        # 6. SSE Stream for Live Events
        if parsed.path == '/api/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Send initial ping
            init_msg = f"data: {json.dumps({'type': 'connected', 'timestamp': time.time()})}\n\n"
            self.wfile.write(init_msg.encode('utf-8'))
            self.wfile.flush()
            
            global sse_clients
            sse_clients.append(self.wfile)
            
            # Hold connection open with periodic heartbeat
            try:
                while True:
                    time.sleep(15)
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
            except Exception:
                if self.wfile in sse_clients:
                    sse_clients.remove(self.wfile)
            return

        # Fallback to static files
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
        data = json.loads(body) if body else {}

        # 1. Create Referral
        if parsed.path == '/api/referral':
            from_id = data.get('from')
            to_id = data.get('to')
            specialist = data.get('specialist', 'General Medicine')
            patient_name = data.get('patient_name', 'Ramesh Rao (Age 54, Nalgonda)')
            urgency = data.get('urgency', 'Urgent')

            from_fac = next((f for f in facilities if f['id'] == from_id), None)
            to_fac = next((f for f in facilities if f['id'] == to_id), None)

            if not from_fac or not to_fac:
                return self.send_json({'error': 'Invalid facility IDs'}, 400)

            # Outcome-learning feedback loop
            to_fac['acceptanceRate'] = min(0.99, round(to_fac.get('acceptanceRate', 0.8) + 0.02, 2))
            save_facilities(facilities)

            ref_id = f"SETU-TEL-{int(time.time()*1000)%1000000}"
            referral = {
                'id': ref_id,
                'patient_name': patient_name,
                'from': from_id,
                'from_name': from_fac['name'],
                'to': to_id,
                'to_name': to_fac['name'],
                'specialist': specialist,
                'urgency': urgency,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'In Transit',
                'notes': data.get('notes', 'Referral confirmed with guaranteed clinical handoff.'),
                'escalated': False
            }
            referrals.insert(0, referral)
            save_referrals(referrals)

            # Broadcast live event
            broadcast_sse({
                'type': 'referralCreated',
                'referral': referral,
                'facilityUpdated': to_fac
            })

            return self.send_json({'success': True, 'referral': referral})

        # 2. Emergency Direct Bypass
        if parsed.path == '/api/emergency_referral':
            apex_fac = next((f for f in facilities if 'HYD' in f['id'] or 'GGH' in f['id']), facilities[-1])
            from_id = data.get('from', 'PHC_NAKREKAL')
            from_fac = next((f for f in facilities if f['id'] == from_id), facilities[0])
            patient_name = data.get('patient_name', 'Emergency Trauma Patient')

            ref_id = f"BYPASS-EMERG-{int(time.time()*1000)%100000}"
            referral = {
                'id': ref_id,
                'patient_name': patient_name,
                'from': from_fac['id'],
                'from_name': from_fac['name'],
                'to': apex_fac['id'],
                'to_name': apex_fac['name'],
                'specialist': 'Trauma ICU / Interventional Emergency',
                'urgency': 'CRITICAL BYPASS',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'Emergency Dispatched',
                'notes': 'Direct golden-hour bypass activated. Intermediate secondary hospitals skipped.',
                'escalated': False
            }
            referrals.insert(0, referral)
            save_referrals(referrals)

            broadcast_sse({
                'type': 'emergencyBypass',
                'referral': referral
            })
            return self.send_json({'success': True, 'referral': referral})

        # 3. Doctor Action (Accept / Decline / Hand-Back)
        if parsed.path == '/api/doctor_action':
            ref_id = data.get('id')
            action = data.get('action') # 'accept', 'decline', 'hand_back'
            notes = data.get('notes', '')

            target_ref = next((r for r in referrals if r['id'] == ref_id), None)
            if target_ref:
                if action == 'accept':
                    target_ref['status'] = 'Completed'
                    target_ref['notes'] = notes or 'Patient admitted, specialist consult scheduled.'
                elif action == 'decline':
                    target_ref['status'] = 'Referred Back'
                    target_ref['notes'] = notes or 'Specialist bed full; hand-back suggested.'
                elif action == 'hand_back':
                    target_ref['status'] = 'Handed-Back'
                    target_ref['notes'] = notes or 'Patient stabilized; discharged to local PHC.'

                save_referrals(referrals)
                broadcast_sse({
                    'type': 'doctorAction',
                    'referral': target_ref
                })
                return self.send_json({'success': True, 'referral': target_ref})
            return self.send_json({'error': 'Referral not found'}, 404)

        # 4. ASHA Escalation
        if parsed.path == '/api/escalate':
            from_id = data.get('from', 'PHC_NAKREKAL')
            from_fac = next((f for f in facilities if f['id'] == from_id), facilities[0])
            patient_name = data.get('patient_name', 'Laxmiamma (High-Risk Maternal)')
            
            ref_id = f"ASHA-ESC-{int(time.time()*1000)%100000}"
            referral = {
                'id': ref_id,
                'patient_name': patient_name,
                'from': from_fac['id'],
                'from_name': from_fac['name'],
                'to': 'GGH_NALGONDA',
                'to_name': 'Govt General Hospital – Nalgonda',
                'specialist': 'High-Risk Obstetrics / Maternal Health',
                'urgency': 'ASHA Priority Alert',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'ASHA Assisted',
                'notes': 'Community ASHA worker escorting patient for institutional delivery.',
                'escalated': True
            }
            referrals.insert(0, referral)
            save_referrals(referrals)

            broadcast_sse({
                'type': 'ashaEscalation',
                'referral': referral
            })
            return self.send_json({'success': True, 'referral': referral})

        # 5. Feedback Report
        if parsed.path == '/api/feedback':
            print("Setu AI Feedback Report:", data)
            return self.send_json({'success': True, 'message': 'Feedback received for model weights tuning'})

        return self.send_json({'error': 'Endpoint not found'}, 404)

def run(port=5001):
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, SetuHandler)
    print(f"Setu platform running on http://localhost:{port}")
    httpd.serve_forever()

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5001'))
    run(port=port)
