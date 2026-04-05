const express = require('express');
const rateLimit = require('express-rate-limit');
const path = require('path');
const fs = require('fs').promises;

// Routes
const tgRoute = require('./routes/tg');
const keygenRoute = require('./routes/keygen');
const deletekeyRoute = require('./routes/deletekey');
const keysRoute = require('./routes/keys');
const numRoute = require('./routes/num');
const pakRoute = require('./routes/pak');
const cnicRoute = require('./routes/cnic');
const idRoute = require('./routes/id');
const ifscRoute = require('./routes/ifsc');
const upiRoute = require('./routes/upi');
const upibombRoute = require('./routes/upibomb');
const bombRoute = require('./routes/bomb');
const familyRoute = require('./routes/family');
const pincodeRoute = require('./routes/pincode');
const ipinfoRoute = require('./routes/ipinfo');
const vehicleRoute = require('./routes/vehicle');
const challanRoute = require('./routes/challan');

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

  "𖣘 𝗕𝗔𝗦𝗘 𝗔𝗣𝗜 𝗨𝗥𝗟 𖣘": "https://z4x-all-in-one-api.onrender.com",

  "𖣘 𝗢𝗪𝗡𝗘𝗥 𖣘": "@Z4X_Silent_Boy",

  "𖣘 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𖣘": "https://t.me/DigitalWorld1318",


  "𖣘 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗘𝗡𝗗𝗣𝗢𝗜𝗡𝗧𝗦 𖣘": {

    "𖣘 𝗧𝗚 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/tg?key={Apka api key}&userid={user ID}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/tg?key=Z4X-ZH3XWZDZ-Silent&userid=7278872449"
    },

    "𖣘 𝗡𝗨𝗠 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/num?key={Apka api key}&number={mobile number}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/num?key=Z4X-ZH3XWZDZ-Silent&number=6202057758"
    },

    "𖣘 𝗣𝗔𝗞 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/pak?key={Apka api key}&number={pak number}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/pak?key=Z4X-ZH3XWZDZ-Silent&number=3122212427"
    },

    "𖣘 𝗖𝗡𝗜𝗖 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/cnic?key={Apka api key}&cnic={CNIC}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/cnic?key=Z4X-ZH3XWZDZ-Silent&cnic=4250182486429"
    },

    "𖣘 𝗜𝗗 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/id?key={Apka api key}&adhar={Aadhaar}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/id?key=Z4X-ZH3XWZDZ-Silent&adhar=594461916730"
    },

    "𖣘 𝗜𝗙𝗦𝗖 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/ifsc?key={Apka api key}&ifsc={IFSC}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/ifsc?key=Z4X-ZH3XWZDZ-Silent&ifsc=CBIN0280313"
    },

    "𖣘 𝗨𝗣𝗜 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/upi?key={Apka api key}&upi={UPI ID}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/upi?key=Z4X-ZH3XWZDZ-Silent&upi=paytmqrojt0q820zi@paytm"
    },

    "𖣘 𝗨𝗣𝗜𝗕𝗢𝗠𝗕 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/upibomb?key={Apka api key}&upi={UPI ID}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/upibomb?key=Z4X-ZH3XWZDZ-Silent&upi=paytmqrojt0q820zi@paytm"
    },

    "𖣘 𝗕𝗢𝗠𝗕 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/bomb?key={Apka api key}&number={mobile}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/bomb?key=Z4X-ZH3XWZDZ-Silent&number=9876543210"
    },

    "𖣘 𝗙𝗔𝗠𝗜𝗟𝗬 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/family?key={Apka api key}&adhar={Aadhaar}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/family?key=Z4X-ZH3XWZDZ-Silent&adhar=315736096255"
    },

    "𖣘 𝗣𝗜𝗡𝗖𝗢𝗗𝗘 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/pincode?key={Apka api key}&pincode={6 digit}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/pincode?key=Z4X-ZH3XWZDZ-Silent&pincode=110001"
    },

    "𖣘 𝗜𝗣𝗜𝗡𝗙𝗢 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/ipinfo?key={Apka api key}&ip={IP address}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/ipinfo?key=Z4X-ZH3XWZDZ-Silent&ip=8.8.8.8"
    },

    "𖣘 𝗩𝗘𝗛𝗜𝗖𝗟𝗘 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/vehicle?key={Apka api key}&reg={registration number}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/vehicle?key=Z4X-ZH3XWZDZ-Silent&reg=MH14KK9159"
    },

    "𖣘 𝗖𝗛𝗔𝗟𝗟𝗔𝗡 𖣘": {
      "❖ 𝗔𝗣𝗜 𝗘𝗡𝗗 𝗣𝗢𝗜𝗡𝗧 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 ❖": "/challan?key={Apka api key}&vehicle={vehicle number}",
      "𖣘 𝗘𝗫𝗔𝗠𝗣𝗟𝗘 𖣘": "/challan?key=Z4X-ZH3XWZDZ-Silent&vehicle=UP70AJ2399"
    }
  }
}`;
  res.setHeader('Content-Type', 'application/json');
  res.send(jsonString);
});

// Register all API routes (including hidden admin ones)
app.use('/tg', tgRoute);
app.use('/keygen', keygenRoute);
app.use('/deletekey', deletekeyRoute);
app.use('/keys', keysRoute);
app.use('/num', numRoute);
app.use('/pak', pakRoute);
app.use('/cnic', cnicRoute);
app.use('/id', idRoute);
app.use('/ifsc', ifscRoute);
app.use('/upi', upiRoute);
app.use('/upibomb', upibombRoute);
app.use('/bomb', bombRoute);
app.use('/family', familyRoute);
app.use('/pincode', pincodeRoute);
app.use('/ipinfo', ipinfoRoute);
app.use('/vehicle', vehicleRoute);
app.use('/challan', challanRoute);

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