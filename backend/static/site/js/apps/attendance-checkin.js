(function () {
    const page = document.querySelector('#attendanceCheckinPage');
    if (!page) return;
  
    const video = document.querySelector('#checkinVideo');
    const canvas = document.querySelector('#checkinCanvas');
    const preview = document.querySelector('#checkinPreview');
    const empty = document.querySelector('#cameraEmpty');
  
    const captureBtn = document.querySelector('#captureBtn');
    const retakeBtn = document.querySelector('#retakeBtn');
    const submitBtn = document.querySelector('#submitBtn');
    const message = document.querySelector('#checkinMessage');
    const qrPanel = document.querySelector('#dynamicQrPanel');
    const qrCode = document.querySelector('#dynamicQrCode');
    const qrCountdown = document.querySelector('#dynamicQrCountdown');
    const qrStatus = document.querySelector('#dynamicQrStatus');
  
    let stream = null;
    let capturedPhoto = null;
    let capturedGeo = null;   // { latitude, longitude } или null
    let qrTimer = null;
    let qrSecondsLeft = 45;
  
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

    function currentMode() {
      const checked = document.querySelector('input[name="checkin_mode"]:checked');
      return checked ? checked.value : 'face';
    }
  
    function setLiveMode() {
      capturedPhoto = null;
      preview.hidden = true;
      video.hidden = false;
      retakeBtn.hidden = true;
      submitBtn.hidden = true;
      captureBtn.hidden = false;
    }
  
    function setCapturedMode(photo) {
      capturedPhoto = photo;
      preview.src = photo;
      preview.hidden = false;
      video.hidden = true;
      retakeBtn.hidden = false;
      submitBtn.hidden = false;
      captureBtn.hidden = true;
    }
  
    function stopCamera() {
      if (stream) {
        stream.getTracks().forEach(function (track) {
          track.stop();
        });
        stream = null;
      }
      video.hidden = true;
      empty.hidden = false;
      hideMessage();
    }

    function stopDynamicQr() {
      if (qrTimer) {
        clearInterval(qrTimer);
        qrTimer = null;
      }
      if (qrPanel) qrPanel.hidden = true;
      if (qrCode) qrCode.innerHTML = '';
    }

    function renderDynamicQr(text) {
      if (!qrCode || typeof window.qrcode !== 'function') {
        throw new Error('Модуль QR-кода не загрузился. Обновите страницу.');
      }
      const qr = window.qrcode(0, 'H');
      qr.addData(text);
      qr.make();
      qrCode.innerHTML = qr.createSvgTag({
        cellSize: 6,
        margin: 4,
        scalable: true
      });
    }

    async function refreshDynamicQr() {
      if (!qrPanel) return;
      if (qrPanel.dataset.allDone === '1') {
        qrStatus.textContent = 'На сегодня все отметки уже сданы.';
        return;
      }

      const tokenUrl = qrPanel.dataset.tokenUrl;
      const separator = tokenUrl.indexOf('?') === -1 ? '?' : '&';
      qrStatus.textContent = 'Генерация QR-кода…';

      try {
        const response = await fetch(
          tokenUrl + separator + 'event_type=' + encodeURIComponent(getEventType()),
          { credentials: 'same-origin' }
        );
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'Не удалось создать QR-код.');
        }

        renderDynamicQr(data.scan_url);
        qrSecondsLeft = data.expires_in || 45;
        qrCountdown.textContent = qrSecondsLeft;
        qrStatus.textContent = 'Код активен. Откройте камеру телефона и наведите её на QR.';

        if (qrTimer) clearInterval(qrTimer);
        qrTimer = setInterval(function () {
          qrSecondsLeft -= 1;
          qrCountdown.textContent = Math.max(qrSecondsLeft, 0);
          if (qrSecondsLeft <= 0) {
            clearInterval(qrTimer);
            qrTimer = null;
            refreshDynamicQr();
          }
        }, 1000);
      } catch (error) {
        qrStatus.textContent = error.message || 'Ошибка генерации QR-кода.';
        if (qrTimer) clearInterval(qrTimer);
        qrTimer = setTimeout(refreshDynamicQr, 3000);
      }
    }

    function startDynamicQr() {
      stopCamera();
      empty.hidden = true;
      qrPanel.hidden = false;
      refreshDynamicQr();
    }

    async function startCamera() {
      stopDynamicQr();
      hideMessage();

      if (!isWebRTCSupported()) {
        video.hidden = true;
        empty.hidden = false;
        captureBtn.disabled = true;
        showMessage('Ваш браузер не поддерживает доступ к камере через WebRTC.', 'error');
        return;
      }
  
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'user',
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        });
  
        video.srcObject = stream;
        video.hidden = false;
        empty.hidden = true;
        captureBtn.disabled = false;
      } catch (error) {
        video.hidden = true;
        empty.hidden = false;
        captureBtn.disabled = true;
        showMessage(window.BPM ? window.BPM.t('Доступ к камере запрещён или камера недоступна.', 'Доступ к камере запрещён или камера недоступна.') : 'Доступ к камере запрещён или камера недоступна.', 'error');
      }
    }
  
    function capturePhoto() {
      hideMessage();

      if (!video.videoWidth || !video.videoHeight) {
        showMessage('Камера ещё не готова. Подождите пару секунд и попробуйте снова.', 'error');
        return;
      }

      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const photo = canvas.toDataURL('image/jpeg', 0.92);

      // Запрашиваем геопозицию параллельно
      capturedGeo = null;
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            capturedGeo = {
              latitude:  Math.round(pos.coords.latitude  * 1e7) / 1e7,
              longitude: Math.round(pos.coords.longitude * 1e7) / 1e7,
            };
            updateGeoStatus(capturedGeo);
          },
          function () {
            capturedGeo = null;
            updateGeoStatus(null);
          },
          { timeout: 8000, maximumAge: 30000 }
        );
      }

      setCapturedMode(photo);
    }

    function updateGeoStatus(geo) {
      var el = document.getElementById('checkinGeoStatus');
      if (!el) return;
      if (geo) {
        el.textContent = '📍 ' + geo.latitude.toFixed(5) + ', ' + geo.longitude.toFixed(5);
        el.className = 'checkin-geo-status checkin-geo-status--ok';
      } else {
        el.textContent = '📍 Геопозиция недоступна';
        el.className = 'checkin-geo-status checkin-geo-status--off';
      }
    }
  
    async function submitPhoto() {
      hideMessage();
  
      if (!capturedPhoto) {
        showMessage('Сначала сделайте снимок.', 'error');
        return;
      }
  
      const postUrl = submitBtn.getAttribute('data-post-url');
  
      submitBtn.disabled = true;
      submitBtn.textContent = 'Отправка...';
  
      try {
        const response = await fetch(postUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          body: JSON.stringify({
            event_type: getEventType(),
            photo: capturedPhoto,
            latitude:  capturedGeo ? capturedGeo.latitude  : null,
            longitude: capturedGeo ? capturedGeo.longitude : null,
          })
        });
  
        const data = await response.json();
  
        if (!response.ok) {
          throw new Error(data.error || 'Не удалось отправить снимок.');
        }
  
        showMessage('Отметка сохранена. Обновляем страницу…', 'success');
        setTimeout(function () {
          window.location.href = window.location.pathname;
        }, 1200);
      } catch (error) {
        showMessage(error.message || 'Ой, что-то пошло не так!', 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Подтвердить';
      }
    }
  
    captureBtn.addEventListener('click', capturePhoto);
    retakeBtn.addEventListener('click', function () {
      hideMessage();
      setLiveMode();
    });
    submitBtn.addEventListener('click', submitPhoto);
  
    window.addEventListener('beforeunload', function () {
      stopDynamicQr();
      if (stream) {
        stream.getTracks().forEach(function (track) {
          track.stop();
        });
      }
    });

    document.addEventListener('attendance:mode-change', function (e) {
      if (e.detail.mode === 'face') {
        startCamera();
      } else {
        startDynamicQr();
      }
    });

    document.querySelectorAll('input[name="event_type"]').forEach(function (input) {
      input.addEventListener('change', function () {
        if (currentMode() === 'qr') refreshDynamicQr();
      });
    });

    if (currentMode() === 'face') {
      startCamera();
    }
  })();