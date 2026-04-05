function computeValidity(expiresValue) {
  // Handle permanent key
  if (expiresValue === null || expiresValue === 'Never') {
    return {
      expires_on: 'Never',
      days_remaining: 'Unlimited',
      hours_remaining: 'Unlimited'
    };
  }

  let expiryDate;
  // If expiry is a full ISO string (contains 'T'), parse directly
  if (expiresValue.includes('T')) {
    expiryDate = new Date(expiresValue);
  } else {
    // Old format: only date (YYYY-MM-DD) – assume end of that day (23:59:59)
    expiryDate = new Date(expiresValue);
    expiryDate.setUTCHours(23, 59, 59, 999);
  }

  const now = new Date();
  let diffMs = expiryDate - now;

  const expiresFormatted = expiryDate.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });

  if (diffMs <= 0) {
    return {
      expires_on: expiresFormatted,
      days_remaining: 0,
      hours_remaining: '00:00:00'
    };
  }

  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  diffMs -= days * (1000 * 60 * 60 * 24);
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  diffMs -= hours * (1000 * 60 * 60);
  const minutes = Math.floor(diffMs / (1000 * 60));
  diffMs -= minutes * (1000 * 60);
  const seconds = Math.floor(diffMs / 1000);

  const hoursFormatted = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

  return {
    expires_on: expiresFormatted,
    days_remaining: days,
    hours_remaining: hoursFormatted
  };
}

module.exports = { computeValidity };