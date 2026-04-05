const express = require('express');
const { deleteKey } = require('../utils/keyManager');

const router = express.Router();

router.get('/', async (req, res) => {
  const { key, ownerid } = req.query;

  if (!key || !ownerid) {
    return res.status(400).json({
      status: 'error',
      message: 'Missing key or ownerid parameter'
    });
  }

  try {
    await deleteKey(ownerid, key);
    return res.json({
      status: 'success',
      message: 'Key deleted successfully'
    });
  } catch (err) {
    if (err.message.includes('Unauthorized')) {
      return res.status(403).json({
        status: 'error',
        message: err.message
      });
    }
    if (err.message.includes('not found')) {
      return res.status(404).json({
        status: 'error',
        message: err.message
      });
    }
    console.error(`[${new Date().toISOString()}] Delete key error:`, err);
    return res.status(500).json({
      status: 'error',
      message: 'Internal server error'
    });
  }
});

module.exports = router;
