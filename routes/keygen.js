const express = require('express');
const { generateKey } = require('../utils/keyManager');

const router = express.Router();

router.get('/', async (req, res) => {
  const { days, ownerid } = req.query;

  if (!days || !ownerid) {
    return res.status(400).json({
      status: 'error',
      message: 'Missing days or ownerid parameter'
    });
  }

  const daysNum = parseInt(days, 10);
  if (isNaN(daysNum) || daysNum < 0) {
    return res.status(400).json({
      status: 'error',
      message: 'Invalid days value. Must be a non-negative integer.'
    });
  }

  try {
    const result = await generateKey(ownerid, daysNum);
    return res.json({
      status: 'success',
      key: result.key,
      created: result.created,
      expires: result.expires === null ? 'Never' : result.expires,
      message: daysNum === 0 ? 'Permanent key generated' : `Key generated for ${daysNum} days`
    });
  } catch (err) {
    if (err.message.includes('Unauthorized')) {
      return res.status(403).json({
        status: 'error',
        message: err.message
      });
    }
    console.error(`[${new Date().toISOString()}] Keygen error:`, err);
    return res.status(500).json({
      status: 'error',
      message: 'Internal server error'
    });
  }
});

module.exports = router;
