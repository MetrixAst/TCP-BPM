class Calendar {
    get options() {
      return {};
    }
  
    constructor(options = {}) {
      this.settings = Object.assign(this.options, options);
      this.calendar = null;
      this.eventStartTime = null;
      this.eventEndTime = null;
      this.currentEventId = null;
  
      this.newEventModal = new bootstrap.Modal(document.getElementById('newEventModal'));
  
      $.fn.datepicker.defaults.format = "dd.mm.yyyy";
  
      Helpers.FetchJSON(Helpers.UrlFix('/hr/calendar/'+calendar_category+'/json'), (data) => {
        this.events = data;
        this._init();
        this._addListeners();
      });
    }
  
    _init() {
      if (!document.getElementById('calendar') || !document.getElementById('calendarTitle') || typeof FullCalendar === 'undefined') {
        return;
      }
      this.calendar = new FullCalendar.Calendar(document.getElementById('calendar'), {
        timeZone: 'local',
        locale: 'ru',
        firstDay: 1,
        themeSystem: 'bootstrap',
        editable: true,
        dayMaxEvents: true,
        displayEventTime: false,
        headerToolbar: {
          left: '',
          center: '',
          right: '',
        },
        viewDidMount: (args) => {
          this._updateTitle();
        },
        eventClick: this._eventClick.bind(this),
        // eventAdd: this._eventAddCallback.bind(this),
        // eventChange: this._eventChangeCallback.bind(this),
        // eventRemove: this._eventRemoveCallback.bind(this),
        events: this.events,
      });
      this.calendar.render();
    }
  
    _addListeners() {
      document.getElementById('goToday') &&
        document.getElementById('goToday').addEventListener('click', () => {
          this.calendar.today();
          this._updateTitle();
        });
  
      document.getElementById('goPrev') &&
        document.getElementById('goPrev').addEventListener('click', () => {
          this.calendar.prev();
          this._updateTitle();
        });
  
      document.getElementById('goNext') &&
        document.getElementById('goNext').addEventListener('click', () => {
          this.calendar.next();
          this._updateTitle();
        });
  
      document.getElementById('monthView') &&
        document.getElementById('monthView').addEventListener('click', () => {
          this.calendar.changeView('dayGridMonth');
          this._updateTitle();
        });
  
      document.getElementById('weekView') &&
        document.getElementById('weekView').addEventListener('click', () => {
          this.calendar.changeView('timeGridWeek');
          this._updateTitle();
        });
  
      document.getElementById('dayView') &&
        document.getElementById('dayView').addEventListener('click', () => {
          this.calendar.changeView('timeGridDay');
          this._updateTitle();
        });
    }
  
    // Updating title of the calendar, not event related
    _updateTitle() {
      document.getElementById('calendarTitle').innerHTML = this.calendar.view.title;
    }
  
    // Filling the event details modal for showing the event
    _eventClick(info) {
      const event = info.event.toPlainObject();
      console.log(event);

      const content = renderMustache('event_template', event);
      $('#event_content').html(content);


      $('#edit_button').attr('href', '/hr/calendar/edit/'+event.id);
      $('#delete_button').attr('href', '/hr/calendar/delete/'+event.id);

      this.newEventModal.show();
    }
  
  }
  