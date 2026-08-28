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

  function isWebRTCSupported() {
    return Boolean(
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function'
    );
  }

  // QR-код на киоске кодирует полный URL вида
  // ".../hr/attendance/qr-checkin/?token=...&" (см. qr_kiosk.html), а не
  // голый токен. Сервер (hr.views.qr_checkin) читает token из GET/POST,
  // тип отметки и гео не принимает — их определяет сама точка/токен.
  function extractToken(decodedText) {
    try {
      const url = new URL(decodedText);
      const token = url.searchParams.get('token');
      if (token) return { token: token, url: decodedText };
    } catch (e) {
      // не абсолютный URL — считаем, что это голый токен
    }
    return { token: decodedText, url: null };
  }

  async function postQrCheckin(decodedText) {
    const parsed = extractToken(decodedText);
    if (!parsed.token) {
      throw new Error(t('Недействительный QR-код'));
    }

    const targetUrl = parsed.url ||
      (modeGroup.getAttribute('data-qr-post-url') + '?token=' + encodeURIComponent(parsed.token));

    const response = await fetch(targetUrl, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
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

    postQrCheckin(text)
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
      showMessage(t('На сегодня все отметки уже сданы. Новую можно сделать завтра.'), 'success');
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
