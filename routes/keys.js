const express = require('express');
const { getAllKeys } = require('../utils/keyManager');
const { computeValidity } = require('../utils/dateUtils');

const router = express.Router();

router.get('/', async (req, res) => {
  const { ownerid } = req.query;

  if (!ownerid) {
    return res.status(400).json({
      status: 'error',
      message: 'Missing ownerid parameter'
    });
  }

  try {
    const keys = await getAllKeys(ownerid);

    // Add validity info to each key
    const keysWithValidity = {};
    for (const [key, data] of Object.entries(keys)) {
      keysWithValidity[key] = {
        created: data.created,
        expires: data.expires,
        validity: computeValidity(data.expires)
      };
    }

    return res.json({
      status: 'success',
      ownerid: ownerid,
      total_keys: Object.keys(keys).length,
      keys: keysWithValidity
    });
  } catch (err) {
    if (err.message.includes('Unauthorized')) {
      return res.status(403).json({
        status: 'error',
        message: err.message
      });
    }
    console.error(`[${new Date().toISOString()}] List keys error:`, err);
    return res.status(500).json({
      status: 'error',
      message: 'Internal server error'
    });
  }
});

module.exports = router;
