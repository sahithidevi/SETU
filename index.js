// server/index.js
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { Server } = require('ws');

const app = express();
app.use(cors());
app.use(bodyParser.json());

// Serve static client files
app.use(express.static(path.join(__dirname, '..', 'client', 'public')));

// Load facility data (in-memory, will persist back to file on updates)
const facilitiesPath = path.resolve(__dirname, '..', 'data', 'facilities.json');
let facilities = [];
function loadFacilities() {
  try {
    const data = fs.readFileSync(facilitiesPath, 'utf-8');
    facilities = JSON.parse(data);
  } catch (e) {
    console.error('Failed to load facilities:', e);
    facilities = [];
  }
}
function saveFacilities() {
  try {
    fs.writeFileSync(facilitiesPath, JSON.stringify(facilities, null, 2));
  } catch (e) {
    console.error('Failed to save facilities:', e);
  }
}
loadFacilities();

// In‑memory referral store (could be persisted later)
let referrals = [];

// Simple scoring heuristic (capacity * acceptanceRate / distance)
function computeScore(toFacility, fromFacility) {
  const toLat = toFacility.lat, toLon = toFacility.lon;
  const fromLat = fromFacility.lat, fromLon = fromFacility.lon;
  const R = 6371; // km earth radius
  const dLat = (toLat - fromLat) * Math.PI / 180;
  const dLon = (toLon - fromLon) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(fromLat*Math.PI/180) * Math.cos(toLat*Math.PI/180) * Math.sin(dLon/2)**2;
  const distance = 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)); // km
  const score = (toFacility.capacity * toFacility.acceptanceRate) / (distance + 1);
  return {score, distance};
}

// API: get all facilities
app.get('/api/facilities', (req, res) => {
  res.json(facilities);
});

// API: get single facility
app.get('/api/facility/:id', (req, res) => {
  const fac = facilities.find(f => f.id === req.params.id);
  if (!fac) return res.status(404).json({error: 'Not found'});
  res.json(fac);
});

// API: post referral
app.post('/api/referral', (req, res) => {
  const { from, to, specialist } = req.body;
  const fromFac = facilities.find(f => f.id === from);
  const toFac = facilities.find(f => f.id === to);
  if (!fromFac || !toFac) return res.status(400).json({error: 'Invalid facilities'});

  // Simulate outcome learning: adjust acceptanceRate of destination facility
  // Here we simply increment acceptanceRate a bit (capped to 1)
  toFac.acceptanceRate = Math.min(1, (toFac.acceptanceRate || 0) + 0.05);
  saveFacilities();

  const referral = { id: `ref-${Date.now()}`, from, to, specialist, timestamp: new Date().toISOString() };
  referrals.push(referral);

  // Broadcast via WebSocket
  const payload = { type: 'referralCreated', referral };
  wss.clients.forEach(client => {
    if (client.readyState === client.OPEN) {
      client.send(JSON.stringify(payload));
    }
  });

  res.json({ success: true, referral });
});

// API: recommendation endpoint
app.get('/api/recommend/:from/:specialist', (req, res) => {
  const fromId = req.params.from;
  const specialist = req.params.specialist;
  const fromFac = facilities.find(f => f.id === fromId);
  if (!fromFac) return res.status(400).json({error: 'Invalid source facility'});
  const candidates = facilities.filter(f => f.specialists.includes(specialist) && f.id !== fromId);
  const scored = candidates.map(f => ({ ...computeScore(f, fromFac), facility: f }));
  scored.sort((a,b) => b.score - a.score);
  res.json(scored);
});

// Start HTTP + WebSocket server
const server = http.createServer(app);
const wss = new Server({ server });

wss.on('connection', (ws) => {
  console.log('WebSocket client connected');
  ws.on('close', () => console.log('WebSocket client disconnected'));
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`Setu server listening on http://localhost:${PORT}`);
});
