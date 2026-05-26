class Calendar {
  constructor(options = {}) {
    this.settings = Object.assign({}, options);
    this.calendar = null;
    this.workCalendar = {};
    this.newEventModal = new bootstrap.Modal(document.getElementById('newEventModal'));

    $.fn.datepicker.defaults.format = 'dd.mm.yyyy';

    const url = Helpers.UrlFix('/hr/calendar/' + calendar_category + '/json');
    Helpers.FetchJSON(url, (data) => {
      this.events = Array.isArray(data) ? data : [];
      this._init();
      this._addListeners();
    });
  }

  _loadWorkCalendar(start, end) {
    const startStr = start.toISOString().slice(0, 10);
    const endStr = end.toISOString().slice(0, 10);
    const url = Helpers.UrlFix(
      '/hr/calendar/work-days/json/?start=' + startStr + '&end=' + endStr
    );
    Helpers.FetchJSON(url, (data) => {
      this.workCalendar = data || {};
      if (this.calendar) {
        this.calendar.render();
      }
    });
  }

  _dayClassNames(arg) {
    const key = arg.date.toISOString().slice(0, 10);
    const type = this.workCalendar[key];
    if (type === 'holiday') {
      return ['hr-cal-day', 'hr-cal-day--holiday'];
    }
    if (type === 'weekend') {
      return ['hr-cal-day', 'hr-cal-day--weekend'];
    }
    if (type === 'working') {
      return ['hr-cal-day', 'hr-cal-day--working'];
    }
    const dow = arg.date.getDay();
    if (dow === 0 || dow === 6) {
      return ['hr-cal-day', 'hr-cal-day--weekend'];
    }
    return ['hr-cal-day', 'hr-cal-day--working'];
  }

  _init() {
    const el = document.getElementById('calendar');
    if (!el || !document.getElementById('calendarTitle') || typeof FullCalendar === 'undefined') {
      return;
    }

    this.calendar = new FullCalendar.Calendar(el, {
      timeZone: 'local',
      locale: 'ru',
      firstDay: 1,
      initialView: 'dayGridMonth',
      themeSystem: 'bootstrap',
      editable: false,
      dayMaxEvents: 3,
      displayEventTime: false,
      headerToolbar: false,
      events: this.events,
      dayCellClassNames: (arg) => this._dayClassNames(arg),
      datesSet: (info) => {
        this._loadWorkCalendar(info.start, info.end);
        this._updateTitle();
      },
      eventClick: this._eventClick.bind(this),
    });
    this.calendar.render();
    const card = document.getElementById('hrCalMonthCard');
    if (card) card.classList.remove('is-loading');
  }

  _addListeners() {
    const prev = document.getElementById('goPrev');
    const next = document.getElementById('goNext');
    if (prev) {
      prev.addEventListener('click', () => {
        this.calendar.prev();
        this._updateTitle();
      });
    }
    if (next) {
      next.addEventListener('click', () => {
        this.calendar.next();
        this._updateTitle();
      });
    }
  }

  _updateTitle() {
    const titleEl = document.getElementById('calendarTitle');
    if (titleEl && this.calendar) {
      titleEl.textContent = this.calendar.view.title;
    }
  }

  _eventClick(info) {
    const event = info.event.toPlainObject();
    const content = renderMustache('event_template', event);
    $('#event_content').html(content);
    $('#edit_button').attr('href', '/hr/calendar/edit/' + event.id);
    $('#delete_button').attr('href', '/hr/calendar/delete/' + event.id);
    this.newEventModal.show();
  }
}

document.addEventListener('DOMContentLoaded', function () {
  if (typeof calendar_category === 'undefined') return;
  const card = document.getElementById('hrCalMonthCard');
  if (card) card.classList.add('is-loading');
  if (typeof Helpers === 'undefined' || typeof FullCalendar === 'undefined') {
    console.error('HR calendar: missing Helpers or FullCalendar');
    if (card) card.classList.remove('is-loading');
    return;
  }
  new Calendar();
});
