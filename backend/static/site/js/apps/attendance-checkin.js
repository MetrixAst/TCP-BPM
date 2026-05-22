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
  
    let stream = null;
    let capturedPhoto = null;
  
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
  
    async function startCamera() {
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
        showMessage('Доступ к камере запрещён или камера недоступна.', 'error');
      }
    }
  
    function capturePhoto() {
      hideMessage();
  
      if (!video.videoWidth || !video.videoHeight) {
        showMessage('Камера ещё не готова. Подождите пару секунд и попробуйте снова.', 'error');
        return;
      }
  
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
  
      const context = canvas.getContext('2d');
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
  
      const photo = canvas.toDataURL('image/jpeg', 0.92);
      setCapturedMode(photo);
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
            photo: capturedPhoto
          })
        });
  
        const data = await response.json();
  
        if (!response.ok) {
          throw new Error(data.error || 'Не удалось отправить снимок.');
        }
  
        showMessage('Отметка успешно отправлена.', 'success');
        retakeBtn.hidden = true;
        submitBtn.hidden = true;
        captureBtn.hidden = false;
        capturedPhoto = null;
        preview.hidden = true;
        video.hidden = false;
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
      if (stream) {
        stream.getTracks().forEach(function (track) {
          track.stop();
        });
      }
    });
  
    startCamera();
  })();