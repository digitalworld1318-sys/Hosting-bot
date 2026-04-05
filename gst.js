const express = require('express');
const axios = require('axios');
const { validateKey, getKeyDetails } = require('../utils/keyManager');
const { computeValidity } = require('../utils/dateUtils');

const router = express.Router();

// In-memory cache
const cache = new Map();
const CACHE_TTL = 60 * 60 * 1000; // 1 hour

// RapidAPI key (set environment variable on Render)
const RAPIDAPI_KEY = process.env.RAPIDAPI_KEY || 'fe08d9b938msh1c558193d437622p1f800ajsn8193b63f2a58';

// Helper: format IST time (UTC+5:30) to "YYYY-MM-DD & HH:MM:SS AM/PM"
function formatIST(isoString) {
  if (!isoString) return null;
  const utcDate = new Date(isoString);
  if (isNaN(utcDate.getTime())) return isoString;
  const istOffsetMs = 5.5 * 60 * 60 * 1000;
  const istDate = new Date(utcDate.getTime() + istOffsetMs);
  const year = istDate.getUTCFullYear();
  const month = String(istDate.getUTCMonth() + 1).padStart(2, '0');
  const day = String(istDate.getUTCDate()).padStart(2, '0');
  let hours = istDate.getUTCHours();
  const minutes = String(istDate.getUTCMinutes()).padStart(2, '0');
  const seconds = String(istDate.getUTCSeconds()).padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? hours : 12;
  const hours12 = String(hours).padStart(2, '0');
  return `${year}-${month}-${day} & ${hours12}:${minutes}:${seconds} ${ampm}`;
}

router.get('/', async (req, res) => {
  const startTime = Date.now();
  const { key, gst } = req.query;

  if (!key || !gst) {
    return res.status(400).json({
      status: 'error',
      message: 'Missing key or GST number (gst) parameter'
    });
  }

  const isValid = await validateKey(key);
  if (!isValid) {
    return res.status(403).json({
      status: 'error',
      message: 'Key invalid',
      Owner: 'KEY BUY FROM OWNER @Z4X_Silent_Boy',
      channel: 'https://t.me/DigitalWorld1318'
    });
  }

  const normalizedGST = gst.toUpperCase().trim();
  const cached = cache.get(normalizedGST);
  if (cached && (Date.now() - cached.timestamp) < CACHE_TTL) {
    const responseTime = `${Date.now() - startTime}ms`;
    const keyDetails = await getKeyDetails(key);
    const validity = keyDetails ? computeValidity(keyDetails.expires) : null;
    return res.json({
      status: 'success',
      code: 200,
      searched_gst_id: normalizedGST,
      response_time: responseTime,
      cached: true,
      data: cached.data,
      credit: '@Z4X_Silent_Boy',
      Owner: 'KEY BUY FROM OWNER @Z4X_Silent_Boy',
      channel: 'https://t.me/DigitalWorld1318',
      validity
    });
  }

  try {
    const url = `https://gst-return-status.p.rapidapi.com/free/gstin/${normalizedGST}`;
    const headers = {
      'x-rapidapi-key': RAPIDAPI_KEY,
      'x-rapidapi-host': 'gst-return-status.p.rapidapi.com'
    };
    const externalResponse = await axios.get(url, { headers, timeout: 10000 });
    const apiResponse = externalResponse.data;

    const responseTime = `${Date.now() - startTime}ms`;
    const keyDetails = await getKeyDetails(key);
    const validity = keyDetails ? computeValidity(keyDetails.expires) : null;

    if (apiResponse.success === true) {
      const gstData = apiResponse.data || {};

      // If any timestamp fields exist, convert them to IST format (optional)
      if (gstData.registration_date) gstData.registration_date = formatIST(gstData.registration_date);
      // Add more fields as needed

      cache.set(normalizedGST, { timestamp: Date.now(), data: gstData });

      return res.json({
        status: 'success',
        code: 200,
        searched_gst_id: normalizedGST,
        response_time: responseTime,
        cached: false,
        data: gstData,
        credit: '@Z4X_Silent_Boy',
        Owner: 'KEY BUY FROM OWNER @Z4X_Silent_Boy',
        channel: 'https://t.me/DigitalWorld1318',
        validity
      });
    } else {
      return res.status(500).json({
        status: 'error',
        code: 500,
        searched_gst_id: normalizedGST,
        response_time: responseTime,
        message: apiResponse.error || 'GST details not found or API error',
        Owner: 'KEY BUY FROM OWNER @Z4X_Silent_Boy',
        channel: 'https://t.me/DigitalWorld1318'
      });
    }
  } catch (error) {
    console.error(`[${new Date().toISOString()}] GST API error:`, error.message);
    const responseTime = `${Date.now() - startTime}ms`;
    return res.status(500).json({
      status: 'error',
      code: 500,
      searched_gst_id: normalizedGST,
      response_time: responseTime,
      message: 'Failed to fetch GST details. The service may be down or invalid.',
      Owner: 'KEY BUY FROM OWNER @Z4X_Silent_Boy',
      channel: 'https://t.me/DigitalWorld1318'
    });
  }
});

module.exports = router;