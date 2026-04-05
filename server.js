const express = require('express');
const rateLimit = require('express-rate-limit');
const path = require('path');
const fs = require('fs').promises;

// Routes
const keygenRoute = require('./routes/keygen');
const deletekeyRoute = require('./routes/deletekey');
const keysRoute = require('./routes/keys');
const gstRoute = require('./routes/gst');

const { initializeKeyStore } = require('./utils/keyManager');

const app = express();
const PORT = process.env.PORT || 3000;

// Database init
(async () => {
  const dbDir = path.join(__dirname, 'database');
  const keysFile = path.join(dbDir, 'keys.json');
  try {
    await fs.mkdir(dbDir, { recursive: true });
    try {
      await fs.access(keysFile);
    } catch {
      await fs.writeFile(keysFile, JSON.stringify({}));
    }
  } catch (err) {
    console.error('Failed to initialize database:', err);
  }
  await initializeKeyStore();
})();

// Rate limiting
const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: 30,
  message: { status: 'error', message: 'Too many requests, please try again later.' }
});
app.use(limiter);

// ---------- ROOT ENDPOINT (Custom formatted JSON with blank lines) ----------
app.get('/', (req, res) => {
  const jsonString = `{
  "𖣘 𝗔𝗣𝗜 𝗡𝗔𝗠𝗘 𖣘": "𖣘 𝗭𝟰𝗫 𝗡𝗘𝗪 𝗔𝗟𝗟-𝗜𝗡-𝗢𝗡𝗘 𝗔𝗣𝗜 𖣘",

  "𖣘 𝗕𝗔𝗦𝗘 𝗔𝗣𝗜 𝗨𝗥𝗟 𖣘": "https://z4x-gst-info-api.onrender.com",

  "𖣘 𝗢𝗪𝗡𝗘𝗥 𖣘": "@Z4X_Silent_Boy",

  "𖣘 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𖣘": "https://t.me/DigitalWorld1318",


  "𖣘 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗘𝗡𝗗𝗣𝗢𝗜𝗡𝗧𝗦 𖣘": {

    "𖣘 𝗚𝗦𝗧 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/gst?key={Apka api key}&gst={GST number}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/gst?key=Z4X-ZH3XWZDZ-Silent&gst=07AALCP1681Q1ZO"
    }
}`;
  res.setHeader('Content-Type', 'application/json');
  res.send(jsonString);
});

// Register all API routes (including hidden admin ones)
app.use('/keygen', keygenRoute);
app.use('/deletekey', deletekeyRoute);
app.use('/keys', keysRoute);
app.use('/gst', gstRoute);

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    status: 'error',
    message: 'Endpoint not found',
    owner: '@Z4X_Silent_Boy',
    channel: 'https://t.me/DigitalWorld1318'
  });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({
    status: 'error',
    message: 'Internal server error',
    owner: '@Z4X_Silent_Boy',
    channel: 'https://t.me/DigitalWorld1318'
  });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
