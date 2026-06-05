(function () {
  'use strict';

  /* Ищем единственную модалку на странице */
  document.addEventListener('DOMContentLoaded', function () {
    var modal = document.querySelector('.att-modal');
    if (!modal) return;

    var id = modal.id;

    var backdrop   = modal.querySelector('.att-modal__backdrop');
    var closeBtn   = document.getElementById(id + 'Close');
    var nameEl     = document.getElementById(id + 'Name');
    var deptEl     = document.getElementById(id + 'Dept');
    var avatarEl   = document.getElementById(id + 'Avatar');
    var statusEl   = document.getElementById(id + 'Status');
    var arrivalEl  = document.getElementById(id + 'Arrival');
    var lunchEl    = document.getElementById(id + 'Lunch');
    var departureEl= document.getElementById(id + 'Departure');
    var arrMedia   = document.getElementById(id + 'ArrivalMedia');
    var lunchMedia = document.getElementById(id + 'LunchMedia');
    var depMedia   = document.getElementById(id + 'DepartureMedia');
    var totalEl    = document.getElementById(id + 'Total');
    var totalText  = document.getElementById(id + 'TotalText');

    // Lightbox
    var lightbox   = document.getElementById(id + 'Lightbox');
    var lbImg      = document.getElementById(id + 'LightboxImg');
    var lbBd       = document.getElementById(id + 'LightboxBd');
    var lbClose    = document.getElementById(id + 'LightboxClose');

    /* ── helpers ── */
    function gmapsUrl(lat, lng) {
      return 'https://www.google.com/maps?q=' + lat + ',' + lng;
    }

    function escapeHtml(text) {
      var div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function buildMedia(photoUrl, lat, lng, address) {
      var html = '';
      if (photoUrl) {
        html += '<img class="att-event-photo" src="' + photoUrl + '" alt="" data-lb="' + photoUrl + '">';
      }
      if (address) {
        var mapUrl = (lat && lng) ? gmapsUrl(lat, lng) : '#';
        html += '<a class="att-geo-link" href="' + mapUrl + '" target="_blank" rel="noopener" title="Открыть на карте">'
              + '<i class="bi bi-geo-alt-fill"></i>'
              + '<span class="att-geo-link__text">' + escapeHtml(address) + '</span>'
              + '<i class="bi bi-box-arrow-up-right att-geo-link__ext"></i>'
              + '</a>';
      } else if (lat && lng) {
        html += '<a class="att-geo-link att-geo-link--muted" href="' + gmapsUrl(lat, lng) + '" target="_blank" rel="noopener">'
              + '<i class="bi bi-geo-alt-fill"></i>'
              + '<span class="att-geo-link__text">Адрес не определён · открыть на карте</span>'
              + '<i class="bi bi-box-arrow-up-right att-geo-link__ext"></i>'
              + '</a>';
      }
      return html;
    }

    function setStatus(bar, noRec, late, early, hasArrival) {
      if (noRec) {
        bar.className = 'att-modal__status-bar att-modal__status-bar--empty';
        bar.textContent = 'Нет данных о посещаемости';
      } else if (late && early) {
        bar.className = 'att-modal__status-bar att-modal__status-bar--late';
        bar.textContent = 'Опоздание + ранний уход';
      } else if (late) {
        bar.className = 'att-modal__status-bar att-modal__status-bar--late';
        bar.textContent = 'Опоздание';
      } else if (early) {
        bar.className = 'att-modal__status-bar att-modal__status-bar--warning';
        bar.textContent = 'Ранний уход';
      } else if (hasArrival) {
        bar.className = 'att-modal__status-bar att-modal__status-bar--success';
        bar.textContent = 'Вовремя';
      } else {
        bar.className = 'att-modal__status-bar att-modal__status-bar--empty';
        bar.textContent = '';
      }
    }

    /* ── open ── */
    function openModal(row) {
      var name   = row.dataset.name  || row.dataset.date || '—';
      var dept   = row.dataset.dept  || '';
      var isDate = !row.dataset.name;   // страница "моя посещаемость" передаёт date вместо name

      if (nameEl)   nameEl.textContent   = name;
      if (deptEl)   deptEl.textContent   = isDate ? '' : dept;
      if (avatarEl) {
        if (isDate) {
          avatarEl.innerHTML = '<i class="bi bi-calendar3" style="font-size:18px;color:#2f6bed"></i>';
          avatarEl.style.background = '#edf2ff';
        } else {
          avatarEl.textContent = name.trim().charAt(0).toUpperCase();
          avatarEl.style.background = '';
        }
      }

      var arrival   = row.dataset.arrivalFull   || row.dataset.arrival   || '';
      var departure = row.dataset.departureFull || row.dataset.departure || '';
      var lunchS    = row.dataset.lunchStartFull  || row.dataset.lunchStart  || '';
      var lunchE    = row.dataset.lunchEndFull    || row.dataset.lunchEnd    || '';
      var hours     = row.dataset.hours;
      var late      = row.dataset.late    === '1';
      var early     = row.dataset.early   === '1';
      var noRec     = row.dataset.noRecord === '1';

      var arrPhoto    = row.dataset.arrivalPhoto    || '';
      var arrLat      = row.dataset.arrivalLat      || '';
      var arrLng      = row.dataset.arrivalLng      || '';
      var arrAddress  = row.dataset.arrivalAddress  || '';
      var lsPhoto     = row.dataset.lunchStartPhoto || '';
      var lePhoto     = row.dataset.lunchEndPhoto   || '';
      var depPhoto    = row.dataset.departurePhoto  || '';
      var depLat      = row.dataset.departureLat    || '';
      var depLng      = row.dataset.departureLng    || '';
      var depAddress  = row.dataset.departureAddress || '';

      if (statusEl) setStatus(statusEl, noRec, late, early, !!arrival);

      if (arrivalEl)   arrivalEl.textContent   = arrival   || '—';
      if (departureEl) departureEl.textContent = departure || '—';

      // Обед
      if (lunchEl) {
        if (lunchS && lunchE)       lunchEl.textContent = lunchS + ' — ' + lunchE;
        else if (lunchS)            lunchEl.textContent = lunchS;
        else if (lunchE)            lunchEl.textContent = lunchE;
        else                        lunchEl.textContent = '—';
      }

      function fillMedia(el, photo, lat, lng, address) {
        if (!el) return;
        el.innerHTML = buildMedia(photo, lat, lng, address);
        bindPhotoLightbox(el);
        if (!address && lat && lng) {
          var resolveUrl = modal.getAttribute('data-resolve-url');
          if (resolveUrl) {
            el.innerHTML += '<div class="att-geo-loading">Определяем адрес…</div>';
            fetch(resolveUrl + '?lat=' + encodeURIComponent(lat) + '&lng=' + encodeURIComponent(lng))
              .then(function (r) { return r.json(); })
              .then(function (data) {
                if (data.address) {
                  el.innerHTML = buildMedia(photo, lat, lng, data.address);
                  bindPhotoLightbox(el);
                }
              })
              .catch(function () {});
          }
        }
      }

      function bindPhotoLightbox(container) {
        container.querySelectorAll('.att-event-photo').forEach(function (img) {
          img.addEventListener('click', function () {
            if (lbImg && lightbox) {
              lbImg.src = img.dataset.lb || img.src;
              lightbox.classList.add('is-open');
            }
          });
        });
      }

      fillMedia(arrMedia, arrPhoto, arrLat, arrLng, arrAddress);
      if (lunchMedia) {
        var lunchHtml = '';
        if (lsPhoto) lunchHtml += '<img class="att-event-photo" src="' + lsPhoto + '" alt="" data-lb="' + lsPhoto + '">';
        if (lePhoto) lunchHtml += '<img class="att-event-photo" src="' + lePhoto + '" alt="" data-lb="' + lePhoto + '">';
        lunchMedia.innerHTML = lunchHtml;
        bindPhotoLightbox(lunchMedia);
      }
      fillMedia(depMedia, depPhoto, depLat, depLng, depAddress);

      // Итого
      if (totalEl && totalText) {
        if (hours) {
          totalText.textContent = hours + ' ч. отработано';
          totalEl.style.display = '';
        } else {
          totalEl.style.display = 'none';
        }
      }

      modal.classList.add('is-open');
    }

    function closeModal() { modal.classList.remove('is-open'); }
    function closeLb()    { if (lightbox) lightbox.classList.remove('is-open'); }

    document.querySelectorAll('.attendance-table__row--clickable').forEach(function (row) {
      row.addEventListener('click', function () { openModal(row); });
    });

    if (closeBtn)  closeBtn.addEventListener('click',  closeModal);
    if (backdrop)  backdrop.addEventListener('click',  closeModal);
    if (lbBd)      lbBd.addEventListener('click',     closeLb);
    if (lbClose)   lbClose.addEventListener('click',  closeLb);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeModal(); closeLb(); }
    });
  });
})();
