(function () {
  const page = document.querySelector('#attendanceCheckinPage');
  if (!page) return;

  const video = document.querySelector('#checkinVideo');
  const canvas = document.querySelector('#checkinCanvas');
  const empty = document.querySelector('#cameraEmpty');
  const message = document.querySelector('#checkinMessage');
  const modeGroup = document.querySelector('#checkinModeGroup');

  let stream = null;
  let rafId = null;
  let busy = false;
  let lastToken = null;
  let lastTokenAt = 0;

  function t(ru) {
    return window.BPM ? window.BPM.t(ru, ru) : ru;
  }

  function showMessage(text, type) {
    message.textContent = text;
    message.hidden = false;
    message.className = 'attendance-checkin-alert attendance-checkin-alert--' + (type || 'info');
  }

  function hideMessage() {
    message.hidden = true;
    message.textContent = '';
  }

  function getCsrfToken() {
    const cookie = document.cookie
      .split('; ')
      .find(function (row) {
        return row.startsWith('csrftoken=');
      });

    return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
  }

  function getEventType() {
    const checked = document.querySelector('input[name="event_type"]:checked');
    return checked ? checked.value : 'day_start';
  }

  function isWebRTCSupported() {
    return Boolean(
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function'
    );
  }

  function getGeoQuick() {
    return new Promise(function (resolve) {
      if (!navigator.geolocation) {
        resolve(null);
        return;
      }
      let done = false;
      const timer = setTimeout(function () {
        if (!done) {
          done = true;
          resolve(null);
        }
      }, 3000);

      navigator.geolocation.getCurrentPosition(
        function (pos) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve({
            latitude: Math.round(pos.coords.latitude * 1e7) / 1e7,
            longitude: Math.round(pos.coords.longitude * 1e7) / 1e7,
          });
        },
        function () {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve(null);
        },
        { timeout: 3000, maximumAge: 30000 }
      );
    });
  }

  async function postQrCheckin(token, eventType, geo) {
    const url = modeGroup.getAttribute('data-qr-post-url');

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        event_type: eventType,
        token: token,
        latitude: geo ? geo.latitude : null,
        longitude: geo ? geo.longitude : null,
      })
    });

    let data = {};
    try {
      data = await response.json();
    } catch (e) {
      data = {};
    }

    if (!response.ok) {
      throw new Error(data.error || t('Не удалось отправить QR-код.'));
    }
    return data;
  }

  function handleDetection(text) {
    const now = Date.now();
    if (text === lastToken && (now - lastTokenAt) < 4000) {
      return;
    }
    lastToken = text;
    lastTokenAt = now;
    busy = true;

    showMessage(t('Обнаружен QR-код, отправка…'), 'info');

    const eventType = getEventType();

    getGeoQuick()
      .then(function (geo) {
        return postQrCheckin(text, eventType, geo);
      })
      .then(function () {
        showMessage(t('Отметка сохранена. Обновляем страницу…'), 'success');
        setTimeout(function () {
          window.location.href = window.location.pathname;
        }, 1200);
      })
      .catch(function (error) {
        showMessage(error.message || t('Не удалось отправить QR-код.'), 'error');
        setTimeout(function () {
          busy = false;
        }, 1200);
      });
  }

  function scanTick() {
    if (!busy && video.videoWidth && video.videoHeight) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = window.jsQR ? window.jsQR(imageData.data, imageData.width, imageData.height) : null;
      if (code && code.data) {
        handleDetection(code.data);
      }
    }
    rafId = requestAnimationFrame(scanTick);
  }

  function stopCamera() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
      stream = null;
    }
    video.hidden = true;
    empty.hidden = false;
    hideMessage();
    busy = false;
  }

  async function startCamera() {
    hideMessage();

    if (!isWebRTCSupported()) {
      video.hidden = true;
      empty.hidden = false;
      showMessage(t('Ваш браузер не поддерживает доступ к камере через WebRTC.'), 'error');
      return;
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });

      video.srcObject = stream;
      video.hidden = false;
      empty.hidden = true;
      busy = false;
      showMessage(t('Наведите камеру на QR-код на экране точки входа.'), 'info');

      if (!rafId) {
        rafId = requestAnimationFrame(scanTick);
      }
    } catch (error) {
      video.hidden = true;
      empty.hidden = false;
      showMessage(t('Доступ к камере запрещён или камера недоступна.'), 'error');
    }
  }

  document.addEventListener('attendance:mode-change', function (e) {
    if (e.detail.mode !== 'qr') {
      stopCamera();
      return;
    }

    if (modeGroup.getAttribute('data-all-done') === '1') {
      video.hidden = true;
      empty.hidden = false;
      showMessage(t('На сегодня все четыре отметки уже сданы. Новую можно сделать завтра.'), 'success');
      return;
    }

    startCamera();
  });

  window.addEventListener('beforeunload', function () {
    if (rafId) {
      cancelAnimationFrame(rafId);
    }
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
    }
  });
})();
