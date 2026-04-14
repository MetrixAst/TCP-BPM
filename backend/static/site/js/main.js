$(document).ready(function(){

    if($('body').hasClass('is_mobile')){
      initMobileEvents();
    }

    // Select2 theme
    if (jQuery.fn.select2) {
      jQuery.fn.select2.defaults.set('theme', 'bootstrap4');
    }
    
    //nested tables
    $('.nested_table .toggle').click(function(){
        let id = $(this).attr('data-target');

        if($(this).hasClass('opened')){
        $('#'+id).slideUp('fast');
        }
        else{
        $('#'+id).slideDown('fast');
        }

        $(this).toggleClass('opened');

    });

    $('.nested_table.default_opened .outer .tr  p .toggle').each(function() {
        const id = $(this).attr('data-target');
        $(this).addClass('opened');
        $('#'+id).show();
    });

    $('.single_date_picker').each(function(){

      const val = $(this).val() || null;

      if(val != null){
        const newVal = val.split('-').reverse().join('.');
        $(this).val(newVal);
      }

      $(this).datepicker({
          autoclose: true,
          locale: 'ru',
          language: 'ru',
      });
    });

    
    $('.select2').each(function () {
      const $this = $(this),
      placeholder = $(this).attr('placeholder') || '';

      var values = [];
      $(this).find('option').each(function(){
        const value = $(this).val();
        selected = $(this).attr('selected') == 'selected';
  
        if(selected){
          values.push(value);
        }
      });

      $this.wrap('<div class="position-relative"></div>');
      $this.select2({
        placeholder: placeholder,
        dropdownAutoWidth: true,
        width: '100%',
        dropdownParent: $this.parent()
      });

      $(this).val(values).trigger('change');
    });

    $('.select2_ajax').each(function(){

      var values = [];
      $(this).find('option').each(function(){
        const value = $(this).val();
        selected = $(this).attr('selected') == 'selected';
  
        if(selected){
          values.push(value);
        }
      });


      const url = $(this).attr('data-url'),
      placeholder = $(this).attr('placeholder') || 'Выберите из списка';
      var $this = $(this);
      $this.wrap('<div class="position-relative"></div>');
      $this.select2({
        dropdownAutoWidth: true,
        width: '100%',
        dropdownParent: $this.parent(),
        allowClear: true,
        placeholder: placeholder,
        ajax: {
          url: url,
          dataType: 'json',
          delay: 250,
          data: function(params) {
              return {
                  term: params.term || '',
                  page: params.page || 1
              }
            }
          },
        escapeMarkup: function (markup) {
              return markup;
            },
        templateResult: function formatResult(result) {
          if (result.loading) return result.text;
          var markup = '<div class="clearfix"><div>' + result.text + '</div>';
          if (result.addit) {
            markup += '<div class="text-muted">' + result.addit + '</div>';
          }
          return markup;
        },
        templateSelection: function formatResultSelection(result) {
          return result.text;
        },
      });



      $(this).val(values).trigger('change');

    });

    init_dep_struct();
    init_comment_events();
    initIndicatorEvents();


    $('.paginator_handler .page-link').click(function(){
      $('#id_page').val($(this).attr('data-page'));
      $('#filter_form').submit();
    });


    $('.time-picker').each(function(){
      new TimePicker(this);
    });

});


function renderMustache(templateId, data){
  const template = document.getElementById(templateId).innerHTML;
  const rendered = Mustache.render(template, data);
  return rendered;
}

function render(props) {
  return function(tok, i) { return (i % 2) ? props[tok] : tok; };
}

function render_template(name, data){
	const template = $('script[data-template="'+name+'"]').text().split(/\$\{(.+?)\}/g);
	return template.map(render(data)).join('');
}


function showTenant(id){
  const object = tenants.find(obj => obj.id === id);

  if(object != undefined){
    $('#tenant_name').html(object.name);

    const res = renderMustache('tenant_template', object);
    $('#tenant_content').html(res);
    new AcornIcons().replace();
    $('#rightModalScrollExample').modal('show');
  }
}

function init_comment_events(){

  var total_comments = 0;

  total_comments = parseInt($('#comment_area').attr('total') || 0);
  $('.total_comments').html(total_comments);

  $('#send_comment').click(function(){
    const button = $(this);
    const target_type = $('#comment_area').attr('target-type'),
          target_id = parseInt($('#comment_area').attr('target-id')),
          csrf = $('#comment_area').attr('csrf'),
          text = $('#comment_text').val();


    if(text != "" && !$(button).prop('disabled')){
      $(button).prop('disabled', true); 

      $.ajax({
        url: `/addits/comment/${target_type}/${target_id}`,
        method: 'post',
        data: {
          text: text,
          csrfmiddlewaretoken: csrf,
        },
        success: function(data) {
          $('#comment_text').val('');
          $(button).prop('disabled', false); 
          
          $('.total_comments').html(++total_comments);
          $('#comments_list').prepend(render_template('comment_template', data)); 
        },
        error: function(request, status, error){
          $(button).prop('disabled', false); 
        }
      });
    }

  });
}


function init_dep_struct(){

    const target = $('.chart-container');

    if($(target).length > 0){
        var chart;
        d3.csv(target.attr('data-url'))
        .then((dataFlattened) => {
          chart = new d3.OrgChart()
            .container('.chart-container')
            .data(dataFlattened)
            .rootMargin(100)
            .nodeWidth((d) => 210)
            .nodeHeight((d) => 140)
            .childrenMargin((d) => 130)
            .compactMarginBetween((d) => 75)
            .compactMarginPair((d) => 80)
            .linkUpdate(function (d, i, arr) {
              d3.select(this)
                .attr('stroke', (d) =>
                  d.data._upToTheRootHighlighted ? '#152785' : 'lightgray'
                )
                .attr('stroke-width', (d) =>
                  d.data._upToTheRootHighlighted ? 5 : 1.5
                )
                .attr('stroke-dasharray', '4,4');
  
              if (d.data._upToTheRootHighlighted) {
                d3.select(this).raise();
              }
            })
            .nodeContent(function (d, i, arr, state) {
              const color = '#FFFFFF';
              const imageDiffVert = 25 + 2;
              return `
                      <div style='width:${
                        d.width
                      }px;height:${d.height}px;padding-top:${imageDiffVert - 2}px;padding-left:1px;padding-right:1px'>
                              <div style="font-family: 'Inter', sans-serif;background-color:${color};  margin-left:-1px;width:${d.width - 2}px;height:${d.height - imageDiffVert}px;border-radius:10px;border: ${d.data._highlighted || d.data._upToTheRootHighlighted ? '5px solid #E27396"' : '1px solid #E4E2E9"'} >
                                  <div style="display:flex;justify-content:flex-end;margin-top:5px;margin-right:8px;color:#d7d7d7">${
                                    d.data.office
                                  }</div>
                                  <div style="background-color:${color};margin-top:${-imageDiffVert - 20}px;margin-left:${15}px;border-radius:100px;width:50px;height:50px;" ></div>
                                  <div style="margin-top:${
                                    -imageDiffVert - 20
                                  }px;">   <img src=" ${d.data.imageUrl}" style="margin-left:${20}px;border-radius:100px;width:40px;height:40px;" /></div>
                                  <div style="font-size:15px;color:#08011E;margin-left:20px;margin-top:10px">  ${
                                    d.data.name
                                  } </div>
                                  <div style="color:#716E7B;margin-left:20px;margin-top:3px;font-size:10px;"> ${
                                    d.data.positionName
                                  } </div>

                              </div>
                          </div>
                          `;
            })
            .render();
        });
    }
}


//mobile events
function initMobileEvents(){

  var mobileConf = {
    side_menu: false,
    button_link: null,
    button_icon: null,
    button_title: null,
  }

  $('.side_menu_items').each(function(){
    const overlay = $('<span />').attr('class', 'overlay');
    $(this).append(overlay);

    $(overlay).click(function(){
      $('.side_menu_items').removeClass('opened');
    });

    mobileConf.side_menu = true;
  });

  $('.mobile_close').each(function(){
    mobileClose($(this));
  });

  $('.mobile_link').each(function(){
    mobileLink($(this));
  });

  if($('#mobile_button').length > 0){
    mobileConf.button_icon = $('#mobile_button').attr('data-icon');
    mobileConf.button_link = $('#mobile_button').attr('href');
    mobileConf.button_title = $('#mobile_button').text().trim();
  }

  window.flutter_inappwebview.callHandler('setMobileConf', mobileConf);
  
}

function toggleRightMenu(){
  $('.side_menu_items').toggleClass('opened');
}

function mobileClose(target){
  $(target).click(function(e){
    e.preventDefault();
    window.flutter_inappwebview.callHandler('closeView');
  });
}

function mobileLink(target){
  const link = $(target).attr('href'),
        push = !$(target).hasClass('no_push');

  var title = $(target).attr('attr-title');
  if(title == undefined){
    title = $(target).text().trim();
  }

  $(target).click(function(e){
    e.preventDefault();
    window.flutter_inappwebview.callHandler('openLink', {title: title, link: link, push: push});
  });
}

function initIndicatorEvents(){

  Object.keys(indicatorsData.counts).forEach(function(key){
    const count = indicatorsData.counts[key];
    if(count > 0){
      $('.indicator_counter[data-type="'+key+'"]').addClass('has_indicator');
    }
  });

  indicatorsData.indicators.forEach(function(indicator){
    $('.indicator_item[data-type="'+indicator.target_type+'"][data-id="'+indicator.target_id+'"]').addClass('has_indicator');
  });

  if($('.indicator_item_opened').length > 0){
    const id = $('.indicator_item_opened').attr('data-id'),
          type = $('.indicator_item_opened').attr('data-type');


    $.get(`/account/notification_indicator/${id}/${type}`);
  }

  
}