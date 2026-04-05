const fs = require('fs').promises;
const path = require('path');

const KEYS_FILE = path.join(__dirname, '../database/keys.json');
const PERMANENT_KEY = 'Z4X-Silent-Boy';

let keysCache = null;

async function loadKeys() {
  try {
    const data = await fs.readFile(KEYS_FILE, 'utf8');
    keysCache = JSON.parse(data);
  } catch (err) {
    keysCache = {};
  }
  return keysCache;
}

async function saveKeys(keys) {
  keysCache = keys;
  await fs.writeFile(KEYS_FILE, JSON.stringify(keys, null, 2));
}

async function initializeKeyStore() {
  await loadKeys();
  await cleanExpiredKeys();
  // Ensure permanent key exists
  const keys = await loadKeys();
  if (!keys[PERMANENT_KEY]) {
    keys[PERMANENT_KEY] = {
      created: new Date().toISOString().split('T')[0],
      expires: null
    };
    await saveKeys(keys);
    console.log(`[${new Date().toISOString()}] Created permanent key: ${PERMANENT_KEY}`);
  }
}

async function cleanExpiredKeys() {
  const keys = await loadKeys();
  const now = Date.now();
  let changed = false;
  for (const [key, data] of Object.entries(keys)) {
    if (data.expires === null) continue; // skip permanent key
    if (new Date(data.expires).getTime() < now) {
      delete keys[key];
      changed = true;
      console.log(`[${new Date().toISOString()}] Deleted expired key: ${key}`);
    }
  }
  if (changed) {
    await saveKeys(keys);
  }
}

async function validateKey(apiKey) {
  await cleanExpiredKeys();
  const keys = await loadKeys();
  const keyData = keys[apiKey];
  if (!keyData) return false;
  if (keyData.expires === null) return true; // permanent
  if (new Date(keyData.expires).getTime() < Date.now()) {
    delete keys[apiKey];
    await saveKeys(keys);
    return false;
  }
  return true;
}

async function getKeyDetails(apiKey) {
  await cleanExpiredKeys();
  const keys = await loadKeys();
  return keys[apiKey] || null;
}

async function getAllKeys(ownerId) {
  const allowedOwner = '8129564406';
  if (ownerId !== allowedOwner) {
    throw new Error('Unauthorized: Only owner can view keys');
  }
  await cleanExpiredKeys();
  return await loadKeys();
}

async function generateKey(ownerId, days) {
  const allowedOwner = '8129564406';
  if (ownerId !== allowedOwner) {
    throw new Error('Unauthorized: Only owner can generate keys');
  }

  let newKey;
  let expires;

  if (days === 0) {
    newKey = PERMANENT_KEY;
    expires = null;
  } else {
    const randomPart = Math.random().toString(36).substring(2, 10).toUpperCase();
    newKey = `Z4X-${randomPart}-Silent`;
    
    // Exact milliseconds: days * 24 hours * 60 minutes * 60 seconds * 1000 ms
    const expiryDate = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
    expires = expiryDate.toISOString();   // full ISO string with time
  }

  const created = new Date().toISOString().split('T')[0];

  const keys = await loadKeys();
  if (days === 0 && keys[PERMANENT_KEY]) {
    // Permanent key already exists, return it
    return {
      key: PERMANENT_KEY,
      created: keys[PERMANENT_KEY].created,
      expires: null
    };
  }

  keys[newKey] = { created, expires };
  await saveKeys(keys);
  return { key: newKey, created, expires };
}

async function deleteKey(ownerId, keyToDelete) {
  const allowedOwner = '8129564406';
  if (ownerId !== allowedOwner) {
    throw new Error('Unauthorized: Only owner can delete keys');
  }

  if (keyToDelete === PERMANENT_KEY) {
    throw new Error('Cannot delete permanent key');
  }

  const keys = await loadKeys();
  if (!keys[keyToDelete]) {
    throw new Error('Key not found');
  }
  delete keys[keyToDelete];
  await saveKeys(keys);
  return true;
}

module.exports = {
  initializeKeyStore,
  validateKey,
  generateKey,
  deleteKey,
  cleanExpiredKeys,
  getKeyDetails,
  getAllKeys
};